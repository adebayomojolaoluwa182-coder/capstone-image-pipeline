"""Resize an S3 image into a JPEG thumbnail for a Step Functions Task."""
import hashlib
import io
import logging
import os
import warnings
from pathlib import PurePosixPath

import boto3
from botocore.exceptions import ClientError
from PIL import Image, ImageOps, UnidentifiedImageError

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
S3 = boto3.client("s3")
Image.MAX_IMAGE_PIXELS = 20_000_000
MAX_BYTES = 10 * 1024 * 1024
THUMBNAIL_SIZE = (300, 300)


def rejected(message):
    return {"success": False, "message": message}


def lambda_handler(event, context):
    """Input: {bucket, key, versionId?}. Output includes success for Choice."""
    bucket, key = event.get("bucket"), event.get("key")
    if bucket != os.environ["SOURCE_BUCKET"]:
        return rejected("The source bucket is not the configured originals bucket.")
    if not isinstance(key, str) or not key or len(key.encode("utf-8")) > 1024:
        return rejected("A valid image object key is required.")
    request = {"Bucket": bucket, "Key": key}
    if event.get("versionId"):
        request["VersionId"] = event["versionId"]
    try:
        response = S3.get_object(**request)
    except ClientError as error:
        if error.response["Error"]["Code"] in ("NoSuchKey", "NoSuchVersion", "404"):
            return rejected("The requested source image was not found.")
        raise  # Service and permission errors remain visible to Step Functions.
    with response["Body"] as stream:
        if response.get("ContentLength", 0) > MAX_BYTES:
            return rejected("The source image exceeds the 10 MiB size limit.")
        payload = stream.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        return rejected("The source image exceeds the 10 MiB size limit.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                if image.format not in ("JPEG", "PNG", "WEBP"):
                    return rejected("Supported formats are JPEG, PNG, and WebP.")
                original_size = image.size
                oriented = ImageOps.exif_transpose(image)
                oriented.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                rgba = oriented.convert("RGBA")
                thumbnail = Image.new("RGB", rgba.size, "white")
                thumbnail.paste(rgba, mask=rgba.getchannel("A"))
                output = io.BytesIO()
                thumbnail.save(output, format="JPEG", quality=85, optimize=True)
                final_size = thumbnail.size
    except (UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        return rejected("The object is not a valid image within the supported limits.")
    digest = hashlib.sha256(payload).hexdigest()[:20]
    stem = PurePosixPath(key).stem[:80] or "image"
    output_key = f"thumbnails/{stem}-{digest}.jpg"
    S3.put_object(Bucket=os.environ["DESTINATION_BUCKET"], Key=output_key,
                  Body=output.getvalue(), ContentType="image/jpeg")
    result = {"success": True, "sourceBucket": bucket, "sourceKey": key,
              "outputBucket": os.environ["DESTINATION_BUCKET"],
              "outputKey": output_key, "originalSize": list(original_size),
              "thumbnailSize": list(final_size)}
    LOG.info("Image resized successfully: %s", result)
    return result
