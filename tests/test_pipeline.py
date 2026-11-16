"""Local integration-style checks using real Pillow and in-memory AWS clients."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
import unittest
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
class ClientError(Exception):
    def __init__(self, response, operation="test"):
        self.response=response
        super().__init__(response["Error"]["Code"])
class FakeS3:
    def __init__(self): self.payload=b""; self.outputs=[]; self.requests=[]; self.error=None
    def get_object(self,**kw):
        self.requests.append(kw)
        if self.error: raise self.error
        return {"Body":io.BytesIO(self.payload),"ContentLength":len(self.payload)}
    def put_object(self,**kw): self.outputs.append(kw)
class FakeSFN:
    def __init__(self): self.calls=[];self.error=None
    def start_execution(self,**kw):
        self.calls.append(kw)
        if self.error: raise self.error
        return {"executionArn":"arn:test:execution"}
S3=FakeS3();SFN=FakeSFN()
sys.modules["boto3"]=types.SimpleNamespace(client=lambda service:S3 if service=="s3" else SFN)
sys.modules["botocore"]=types.ModuleType("botocore")
sys.modules["botocore.exceptions"]=types.SimpleNamespace(ClientError=ClientError)
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/"src"/(name+".py"));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
resize=load("resize_image");starter=load("start_from_s3")
class PipelineTests(unittest.TestCase):
    def setUp(self):
        S3.outputs=[];S3.requests=[];S3.error=None;SFN.calls=[];SFN.error=None
        os.environ.update(SOURCE_BUCKET="originals",DESTINATION_BUCKET="thumbs",STATE_MACHINE_ARN="arn:test:workflow")
        data=io.BytesIO();Image.new("RGBA",(1200,800),(20,100,200,128)).save(data,"PNG");S3.payload=data.getvalue()
    def test_real_resize_and_saved_content(self):
        result=resize.lambda_handler({"bucket":"originals","key":"folder/a.png","versionId":"v1"},None)
        self.assertTrue(result["success"]);self.assertEqual(result["thumbnailSize"],[300,200]);self.assertEqual(S3.requests[0]["VersionId"],"v1")
        with Image.open(io.BytesIO(S3.outputs[0]["Body"])) as image:self.assertEqual((image.size,image.format,image.mode),((300,200),"JPEG","RGB"))
    def test_repeat_uses_same_output_key(self):
        event={"bucket":"originals","key":"a.png"};self.assertEqual(resize.lambda_handler(event,None)["outputKey"],resize.lambda_handler(event,None)["outputKey"])
    def test_small_image_not_enlarged(self):
        data=io.BytesIO();Image.new("RGB",(20,10)).save(data,"JPEG");S3.payload=data.getvalue()
        self.assertEqual(resize.lambda_handler({"bucket":"originals","key":"tiny.jpg"},None)["thumbnailSize"],[20,10])
    def test_invalid_bytes_follow_failure_branch(self):
        S3.payload=b"not an image";self.assertFalse(resize.lambda_handler({"bucket":"originals","key":"bad.png"},None)["success"]);self.assertFalse(S3.outputs)
    def test_wrong_bucket_does_not_read(self):
        self.assertFalse(resize.lambda_handler({"bucket":"other","key":"a.png"},None)["success"]);self.assertFalse(S3.requests)
    def test_missing_key_and_missing_object(self):
        self.assertFalse(resize.lambda_handler({"bucket":"originals"},None)["success"])
        S3.error=ClientError({"Error":{"Code":"NoSuchKey"}})
        self.assertFalse(resize.lambda_handler({"bucket":"originals","key":"missing.jpg"},None)["success"])
    def test_oversized_input_is_rejected(self):
        S3.payload=b"x"*(resize.MAX_BYTES+1)
        self.assertFalse(resize.lambda_handler({"bucket":"originals","key":"large.png"},None)["success"])
    def test_service_errors_are_not_reported_as_success(self):
        S3.error=ClientError({"Error":{"Code":"AccessDenied"}})
        with self.assertRaises(ClientError):resize.lambda_handler({"bucket":"originals","key":"a.png"},None)
    def test_s3_trigger_decodes_key_and_deduplicates(self):
        event={"Records":[{"eventName":"ObjectCreated:Put","s3":{"bucket":{"name":"originals"},"object":{"key":"folder%2Fmy+image.png","versionId":"v1","sequencer":"ABC"}}}]}
        starter.lambda_handler(event,None);starter.lambda_handler(event,None)
        self.assertEqual(SFN.calls[0]["name"],SFN.calls[1]["name"])
        self.assertEqual(json.loads(SFN.calls[0]["input"]),{"bucket":"originals","key":"folder/my image.png","versionId":"v1"})
        SFN.error=ClientError({"Error":{"Code":"ExecutionAlreadyExists"}});starter.lambda_handler(event,None)
if __name__=="__main__":unittest.main(verbosity=2)
