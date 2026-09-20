# kotlinx.serialization keeps its generated serializers via @Serializable.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class **$$serializer { *; }
-keepclasseswithmembers class ** {
    @kotlinx.serialization.Serializable <fields>;
}
# Retrofit interfaces are reflective.
-keep,allowobfuscation interface dev.potholewatch.app.data.api.PotholeApi
-keepattributes Signature, Exceptions
