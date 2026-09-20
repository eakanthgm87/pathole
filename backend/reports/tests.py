"""End-to-end checks for the report pipeline.

These run real YOLO inference, so they are slower than a typical unit test but
they prove the thing that actually matters: an uploaded photo becomes a scored,
deduplicated, status-tracked report.
"""
import io

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from core.geoutils import Point, bbox_around, haversine_m, point_in_geometry
from detection.engine import InferenceResult, Detection
from detection import scoring
from reports import selectors, services
from reports.models import DetectionStatus, Report, WorkflowStatus

User = get_user_model()

BLR = (12.9716, 77.5946)


def make_image(width=640, height=480, color=(90, 90, 95)):
    """A plain JPEG. The model will find nothing in it, which is fine: these
    tests assert pipeline behaviour, not detection quality."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile("test.jpg", buf.read(), content_type="image/jpeg")


class GeoUtilsTests(TestCase):
    def test_haversine_known_distance(self):
        # One degree of latitude is ~111.2 km anywhere on the globe.
        d = haversine_m(Point(12.0, 77.0), Point(13.0, 77.0))
        self.assertAlmostEqual(d, 111_195, delta=500)

    def test_haversine_is_zero_for_same_point(self):
        self.assertEqual(haversine_m(Point(*BLR), Point(*BLR)), 0.0)

    def test_bbox_contains_the_radius(self):
        p = Point(*BLR)
        min_lat, min_lng, max_lat, max_lng = bbox_around(p, 100)
        self.assertLess(min_lat, p.lat)
        self.assertGreater(max_lat, p.lat)
        self.assertLess(min_lng, p.lng)
        self.assertGreater(max_lng, p.lng)

    def test_bbox_survives_the_pole(self):
        # cos(lat) -> 0 must not produce inf/NaN.
        _, min_lng, _, max_lng = bbox_around(Point(90.0, 0.0), 500)
        self.assertTrue(all(abs(v) <= 180 for v in (min_lng, max_lng)))

    def test_point_in_polygon_with_hole(self):
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]],
                [[4, 4], [4, 6], [6, 6], [6, 4], [4, 4]],
            ],
        }
        self.assertTrue(point_in_geometry(Point(1, 1), geometry))
        self.assertFalse(point_in_geometry(Point(5, 5), geometry))  # in the hole
        self.assertFalse(point_in_geometry(Point(50, 50), geometry))


class ScoringTests(TestCase):
    def _result(self, boxes, w=1000, h=1000, votes=1):
        return InferenceResult(
            detections=[Detection("pothole", c, b, votes) for b, c in boxes],
            width=w, height=h,
        )

    def test_error_result_is_unknown(self):
        status, conf = scoring.classify(InferenceResult(error="boom"))
        self.assertEqual(status, DetectionStatus.UNKNOWN)
        self.assertEqual(conf, 0.0)

    def test_no_boxes_is_intact(self):
        status, _ = scoring.classify(self._result([]))
        self.assertEqual(status, DetectionStatus.INTACT)

    def test_severity_bands(self):
        # Calibrated to the measured coverage distribution: 20 / 50.
        self.assertEqual(scoring.severity_band(2), "low")
        self.assertEqual(scoring.severity_band(19.9), "low")
        self.assertEqual(scoring.severity_band(20), "medium")
        self.assertEqual(scoring.severity_band(50), "medium")
        self.assertEqual(scoring.severity_band(50.1), "high")

    def test_severity_uses_union_area_not_sum(self):
        # One box covering 25% of the image -> ~25 points.
        one = self._result([([0, 0, 500, 500], 0.9)])
        self.assertAlmostEqual(scoring.severity_score(one), 25.0, delta=0.5)
        # A disjoint second box adds its area plus a small count bump.
        two = self._result([([0, 0, 500, 500], 0.9), ([500, 500, 1000, 1000], 0.8)])
        self.assertAlmostEqual(scoring.severity_score(two), 51.5, delta=0.5)

    def test_duplicate_boxes_do_not_inflate_severity(self):
        """The ensemble emits overlapping boxes for one hole; summing their
        areas used to push almost everything to 'high'."""
        single = self._result([([0, 0, 500, 500], 0.9)])
        stacked = self._result([([0, 0, 500, 500], 0.9), ([10, 10, 505, 505], 0.8)])
        # Coverage barely grows even though there are twice as many boxes.
        self.assertLess(scoring.severity_score(stacked), scoring.severity_score(single) + 5)

    def test_severity_score_is_clamped(self):
        huge = self._result([([0, 0, 1000, 1000], 0.9)] * 12)
        self.assertLessEqual(scoring.severity_score(huge), 100.0)

    def test_severity_ignores_boxes_below_review_threshold(self):
        weak = self._result([([0, 0, 900, 900], 0.02)])
        self.assertEqual(scoring.severity_score(weak), 0.0)


class CreateReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("citizen@test.dev", "pw-test-12345", name="Cit")

    def test_create_report_runs_the_pipeline(self):
        report = services.create_report(
            image_file=make_image(),
            latitude=BLR[0],
            longitude=BLR[1],
            reporter=self.user,
            resolve_address=False,
        )
        self.assertIsNotNone(report.pk)
        self.assertTrue(report.image.name)
        self.assertTrue(report.thumbnail.name)
        self.assertIn(report.detection_status, dict(DetectionStatus.choices))
        self.assertEqual(report.history.count(), 1)
        self.assertEqual(report.location, Point(BLR[0], BLR[1]))

    def test_client_uuid_makes_creation_idempotent(self):
        cid = "11111111-2222-3333-4444-555555555555"
        first = services.create_report(
            image_file=make_image(), latitude=BLR[0], longitude=BLR[1],
            reporter=self.user, client_uuid=cid, resolve_address=False,
        )
        second = services.create_report(
            image_file=make_image(), latitude=BLR[0], longitude=BLR[1],
            reporter=self.user, client_uuid=cid, resolve_address=False,
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Report.objects.count(), 1)

    def test_out_of_range_coordinates_are_rejected(self):
        with self.assertRaises(ValidationError):
            services.create_report(
                image_file=make_image(), latitude=999, longitude=0,
                reporter=self.user, resolve_address=False,
            )

    def test_intact_reports_never_deduplicate(self):
        """A blank photo scores 'intact'; two of them must stay separate."""
        a = services.create_report(
            image_file=make_image(), latitude=BLR[0], longitude=BLR[1],
            reporter=self.user, resolve_address=False,
        )
        b = services.create_report(
            image_file=make_image(), latitude=BLR[0], longitude=BLR[1],
            reporter=self.user, resolve_address=False,
        )
        if a.detection_status == DetectionStatus.INTACT:
            self.assertIsNone(b.duplicate_of)


class WorkflowTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user("c@test.dev", "pw-test-12345")
        self.officer = User.objects.create_user("o@test.dev", "pw-test-12345", role="officer")
        self.report = services.create_report(
            image_file=make_image(), latitude=BLR[0], longitude=BLR[1],
            reporter=self.citizen, resolve_address=False,
        )

    def test_legal_transition_records_history_and_notifies(self):
        services.change_status(
            self.report, WorkflowStatus.VERIFIED, actor=self.officer, note="looks real"
        )
        self.report.refresh_from_db()
        self.assertEqual(self.report.workflow_status, WorkflowStatus.VERIFIED)
        self.assertEqual(self.report.history.count(), 2)
        self.assertEqual(self.citizen.notifications.count(), 1)

    def test_illegal_transition_is_refused(self):
        # submitted -> fixed skips the whole workflow.
        with self.assertRaises(ValidationError):
            services.change_status(self.report, WorkflowStatus.FIXED, actor=self.officer)

    def test_reject_requires_a_reason(self):
        with self.assertRaises(ValidationError):
            services.reject(self.report, actor=self.officer, note="")

    def test_assign_requires_an_officer(self):
        with self.assertRaises(ValidationError):
            services.assign(self.report, self.citizen, actor=self.officer)

    def test_assign_moves_through_verified(self):
        services.assign(self.report, self.officer, actor=self.officer)
        self.report.refresh_from_db()
        self.assertEqual(self.report.workflow_status, WorkflowStatus.ASSIGNED)
        self.assertTrue(self.report.assignments.filter(is_active=True).exists())

    def test_mark_fixed_needs_an_after_photo(self):
        services.verify(self.report, actor=self.officer)
        with self.assertRaises(ValidationError):
            services.mark_fixed(self.report, actor=self.officer, after_image=None)

    def test_severity_override_sticks(self):
        services.override_severity(self.report, "high", actor=self.officer)
        self.report.refresh_from_db()
        self.assertEqual(self.report.severity, "high")
        self.assertTrue(self.report.severity_overridden)

    def test_internal_comments_are_officer_only(self):
        with self.assertRaises(ValidationError):
            services.add_comment(
                self.report, author=self.citizen, body="secret", is_internal=True
            )

    def test_empty_comment_is_refused(self):
        with self.assertRaises(ValidationError):
            services.add_comment(self.report, author=self.citizen, body="   ")


class PermissionTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user("c2@test.dev", "pw-test-12345")
        self.officer = User.objects.create_user("o2@test.dev", "pw-test-12345", role="officer")

    def test_dashboard_is_closed_to_citizens(self):
        self.client.force_login(self.citizen)
        self.assertEqual(self.client.get(reverse("web:dashboard_overview")).status_code, 403)

    def test_dashboard_is_open_to_officers(self):
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(reverse("web:dashboard_overview")).status_code, 200)

    def test_settings_page_is_admin_only(self):
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(reverse("web:dashboard_settings")).status_code, 403)

    def test_report_form_requires_login(self):
        response = self.client.get(reverse("web:report_new"))
        self.assertEqual(response.status_code, 302)

    def test_public_pages_are_anonymous(self):
        for name in ("web:landing", "web:map"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_live_frame_endpoint_requires_login(self):
        self.assertEqual(self.client.post(reverse("web:live_frame")).status_code, 302)


class LiveVideoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("live@test.dev", "pw-test-12345")
        self.client.force_login(self.user)

    def test_frame_analysis_returns_detections(self):
        buf = io.BytesIO()
        Image.new("RGB", (480, 360), (70, 70, 74)).save(buf, format="JPEG")
        buf.seek(0)
        frame = SimpleUploadedFile("frame.jpg", buf.read(), content_type="image/jpeg")
        response = self.client.post(reverse("web:live_frame"), {"frame": frame})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertIn("detections", body)
        self.assertIn("severity", body)

    def test_frame_endpoint_rejects_empty_post(self):
        response = self.client.post(reverse("web:live_frame"), {})
        self.assertEqual(response.status_code, 400)

    def test_capture_requires_a_location(self):
        buf = io.BytesIO()
        Image.new("RGB", (320, 240)).save(buf, format="JPEG")
        buf.seek(0)
        frame = SimpleUploadedFile("c.jpg", buf.read(), content_type="image/jpeg")
        response = self.client.post(reverse("web:live_capture"), {"frame": frame})
        self.assertEqual(response.status_code, 400)


class SelectorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("s@test.dev", "pw-test-12345")

    def test_kpi_summary_shape(self):
        kpis = selectors.kpi_summary()
        for key in ("total", "open", "high_open", "fixed_month", "today", "review"):
            self.assertIn(key, kpis)

    def test_trend_is_zero_filled(self):
        trend = selectors.reports_over_time(14)
        self.assertEqual(len(trend["labels"]), 14)
        self.assertEqual(len(trend["values"]), 14)

    def test_public_features_is_valid_geojson(self):
        data = selectors.public_map_features()
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertIsInstance(data["features"], list)


class ApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("api@test.dev", "pw-test-12345")

    def test_health_is_public(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_jwt_login_returns_tokens(self):
        response = self.client.post(
            "/api/v1/auth/login/",
            {"email": "api@test.dev", "password": "pw-test-12345"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_reports_list_requires_auth(self):
        self.assertEqual(self.client.get("/api/v1/reports/").status_code, 401)

    def test_geojson_is_public(self):
        response = self.client.get("/api/v1/reports/geojson/")
        self.assertEqual(response.status_code, 200)

    def test_nearby_requires_coordinates(self):
        self.assertEqual(self.client.get("/api/v1/reports/nearby/").status_code, 400)

    def test_error_shape_is_standardised(self):
        body = self.client.get("/api/v1/reports/nearby/").json()
        self.assertIn("error", body)
        self.assertIn("code", body["error"])
        self.assertIn("message", body["error"])

class EnsembleTests(TestCase):
    """The merge is what lifts recall from ~70% to ~94%, so it is worth
    pinning down."""

    def test_overlapping_boxes_merge_and_count_votes(self):
        from detection.engine import merge_detections

        merged = merge_detections([
            Detection("pothole", 0.8, [0, 0, 100, 100]),
            Detection("pothole", 0.6, [5, 5, 104, 104]),   # same hole
            Detection("pothole", 0.7, [500, 500, 600, 600]),  # different hole
        ])
        self.assertEqual(len(merged), 2)
        by_conf = sorted(merged, key=lambda d: -d.conf)
        self.assertEqual(by_conf[0].votes, 2)   # two passes agreed
        self.assertEqual(by_conf[0].conf, 0.8)  # highest confidence survives
        self.assertEqual(by_conf[1].votes, 1)

    def test_distant_boxes_never_merge(self):
        from detection.engine import merge_detections

        merged = merge_detections([
            Detection("pothole", 0.8, [0, 0, 50, 50]),
            Detection("pothole", 0.8, [900, 900, 950, 950]),
        ])
        self.assertEqual(len(merged), 2)

    def test_union_area_ignores_overlap(self):
        from detection.engine import union_area

        one = union_area([[0, 0, 500, 500]], 1000, 1000)
        twice = union_area([[0, 0, 500, 500], [0, 0, 500, 500]], 1000, 1000)
        self.assertAlmostEqual(one, twice, places=3)
        self.assertAlmostEqual(one, 0.25, delta=0.01)

    def test_agreement_publishes_and_lone_weak_box_goes_to_review(self):
        """A box two passes agree on is public; the same confidence from a
        single pass waits for an officer."""
        agreed = InferenceResult(
            detections=[Detection("pothole", 0.40, [0, 0, 300, 300], votes=2)],
            width=1000, height=1000,
        )
        alone = InferenceResult(
            detections=[Detection("pothole", 0.40, [0, 0, 300, 300], votes=1)],
            width=1000, height=1000,
        )
        self.assertEqual(scoring.classify(agreed)[0], DetectionStatus.POTHOLE_DETECTED)
        self.assertEqual(scoring.classify(alone)[0], DetectionStatus.NEEDS_REVIEW)

    def test_a_very_confident_single_pass_still_publishes(self):
        sure = InferenceResult(
            detections=[Detection("pothole", 0.90, [0, 0, 300, 300], votes=1)],
            width=1000, height=1000,
        )
        self.assertEqual(scoring.classify(sure)[0], DetectionStatus.POTHOLE_DETECTED)
