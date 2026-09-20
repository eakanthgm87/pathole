pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven("https://repo.osgeo.org/repository/release/")
        maven("https://jitpack.io")
    }
}
rootProject.name = "PotholeWatch"
include(":app")
