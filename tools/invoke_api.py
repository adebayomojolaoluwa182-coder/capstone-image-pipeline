"""Send a SigV4-authenticated request using locally configured AWS credentials."""
import argparse
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

parser=argparse.ArgumentParser()
parser.add_argument("--url",required=True)
parser.add_argument("--bucket",required=True)
parser.add_argument("--key",required=True)
parser.add_argument("--region",default="us-east-1")
args=parser.parse_args()
session=boto3.Session(region_name=args.region)
credentials=session.get_credentials()
if not credentials: raise SystemExit("No AWS session found. Sign in with your own AWS profile or temporary credentials first.")
data=json.dumps({"bucket":args.bucket,"key":args.key}).encode()
request=AWSRequest(method="POST",url=args.url,data=data,headers={"Content-Type":"application/json"})
SigV4Auth(credentials.get_frozen_credentials(),"execute-api",args.region).add_auth(request)
prepared=request.prepare()
try:
    with urlopen(Request(args.url,data=data,headers=dict(prepared.headers),method="POST"),timeout=30) as response:
        print(response.status);print(response.read().decode())
except HTTPError as error:
    print(error.code);print(error.read().decode());raise SystemExit(1)

