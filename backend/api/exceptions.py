from rest_framework.views import exception_handler


def standard_exception_handler(exc, context):
    """Force every error into the documented shape:
    {"error": {"code": ..., "message": ..., "fields": {...}}}
    """
    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    code = getattr(exc, "default_code", "error")
    fields = {}
    if isinstance(detail, dict):
        if "detail" in detail:
            message = str(detail["detail"])
        else:
            fields = {k: [str(m) for m in (v if isinstance(v, list) else [v])]
                      for k, v in detail.items()}
            message = "Validation failed."
    elif isinstance(detail, list):
        message = "; ".join(str(d) for d in detail)
    else:
        message = str(detail)

    payload = {"error": {"code": code, "message": message}}
    if fields:
        payload["error"]["fields"] = fields
    response.data = payload
    return response
