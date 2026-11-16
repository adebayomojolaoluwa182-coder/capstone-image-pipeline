# Verified capstone deployment

Tested on November 16, 2026 in Northern Virginia (`us-east-1`).

| Output | Deployed value |
| --- | --- |
| CloudFormation stack | `comp200-capstone` |
| Originals bucket | `comp200-capstone-originals-666952271625-us-east-1` |
| Thumbnails bucket | `comp200-capstone-thumbnails-666952271625-us-east-1` |
| Workflow | `arn:aws:states:us-east-1:666952271625:stateMachine:comp200-capstone-workflow` |
| API endpoint | `https://9e1i184pmb.execute-api.us-east-1.amazonaws.com/demo/process` |
| API route and authorization | `POST /process`, AWS IAM |
| Pillow layer | `arn:aws:lambda:us-east-1:666952271625:layer:capstone-pillow:1` |

The endpoint requires a signed request from an authorized AWS identity. It is not an anonymous image-processing endpoint. Do not share AWS credentials in the repository or video.

## Test results

1. Uploaded `demo-landscape.png` (1200 × 800) to the originals bucket. The S3-created notification invoked the starter Lambda and automatically started an `s3-` execution.
2. The automatic execution succeeded in 1.545 seconds, running `ResizeImage → ResizeSuccessful → ProcessingSucceeded`.
3. The result reported `success: true`, `originalSize: [1200, 800]`, and `thumbnailSize: [300, 200]`.
4. Downloaded the actual S3 output `thumbnails/demo-landscape-876ebf6f16b461ca822e.jpg`. Pillow independently verified that the downloaded file was a 300 × 200 JPEG (6,598 bytes).
5. API Gateway's console method test returned HTTP 200 and started execution `afa802de-36d2-423f-baca-5d15a1f1bd90`. That execution succeeded in 0.426 seconds. This verifies the integration; the console method test bypasses external caller authorization. A separate external SigV4 client request was not performed.
6. A controlled missing-object execution `7df94af7-38d7-4432-9550-4c52d43259d4` reached `ProcessingFailed` with `ImageProcessingFailed`. The least-privilege S3 role cannot list the bucket, so a missing key can produce S3 AccessDenied rather than NoSuchKey; in that case the Task's Catch route handles it.
7. All nine local tests passed before deployment. They use actual Pillow transformations with simulated AWS clients.

The demonstration video is a captioned walkthrough assembled from actual AWS screenshots and the downloaded thumbnail, rather than a continuous live screen recording. The local video and evidence are excluded from Git; submit the MP4 separately as requested by the assignment.

After grading, follow the cleanup guidance in the README. Both S3 buckets are retained on stack deletion to avoid accidental data loss.
