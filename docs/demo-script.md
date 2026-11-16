# Capstone video outline

Aim for about two to three minutes. Record actual deployed results. Do not show login credentials, access keys, or unrelated personal browser tabs.

1. **Introduction** — “My project creates image thumbnails with S3, Lambda, Step Functions, and API Gateway.” Show the architecture in the README.
2. **Original image** — Show `demo-landscape.png`, which is 1200 by 800 pixels. Upload it to the originals bucket.
3. **Automatic workflow** — Open the new Step Functions execution. Show ResizeImage, ResizeSuccessful, and ProcessingSucceeded. Open the Task output and point out the 300 by 200 thumbnail dimensions.
4. **Actual thumbnail** — Show the thumbnail object in the second S3 bucket. Download or open it and compare it with the original.
5. **API trigger** — In API Gateway's POST /process test panel, submit the original bucket and key. Show the returned execution ARN and the successful API-started execution. Explain that the deployed endpoint uses AWS IAM authentication.
6. **Failure path** — If time permits, run the workflow with a missing object key. Show that it follows the failure path rather than reporting success.
7. **Conclusion** — Show the GitHub repository and README. “The repository contains the Lambda source, state machine, deployment template, and instructions.”

Submit the video and your real GitHub repository link. A script alone does not satisfy the required demonstration video.
