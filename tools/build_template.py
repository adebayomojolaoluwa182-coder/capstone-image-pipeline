"""Generate a reviewable CloudFormation template from the source files."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def sub(value): return {"Fn::Sub": value}
def ref(name): return {"Ref": name}
def arn(name): return {"Fn::GetAtt": [name, "Arn"]}
def statement(actions, resource):
    return {"Effect": "Allow", "Action": actions, "Resource": resource}
def role(service, statements):
    return {"Type": "AWS::IAM::Role", "Properties": {
        "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{
            "Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}]},
        "Policies": [{"PolicyName": "CapstoneResourceAccess", "PolicyDocument": {
            "Version": "2012-10-17", "Statement": statements}}]}}
def bucket_name(kind): return sub("${AWS::StackName}-"+kind+"-${AWS::AccountId}-${AWS::Region}")
def bucket_arn(kind): return sub("arn:${AWS::Partition}:s3:::${AWS::StackName}-"+kind+"-${AWS::AccountId}-${AWS::Region}")
def log_policy(name):
    return statement(["logs:CreateLogStream", "logs:PutLogEvents"],
        sub("arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${AWS::StackName}-"+name+":*"))
r={}
for name in ["Resize", "Starter"]:
    r[name+"Logs"]={"Type":"AWS::Logs::LogGroup", "Properties":{
        "LogGroupName":sub("/aws/lambda/${AWS::StackName}-"+name.lower()), "RetentionInDays":7}}
r["ResizeRole"]=role("lambda.amazonaws.com",[
    statement(["s3:GetObject", "s3:GetObjectVersion"],sub("arn:${AWS::Partition}:s3:::${AWS::StackName}-originals-${AWS::AccountId}-${AWS::Region}/*")),
    statement("s3:PutObject",sub("arn:${AWS::Partition}:s3:::${AWS::StackName}-thumbnails-${AWS::AccountId}-${AWS::Region}/thumbnails/*")),log_policy("resize")])
r["Resize"]={"Type":"AWS::Lambda::Function","DependsOn":"ResizeLogs","Properties":{
    "FunctionName":sub("${AWS::StackName}-resize"),"Runtime":"python3.12","Architectures":["x86_64"],
    "Handler":"index.lambda_handler","Role":arn("ResizeRole"),"Timeout":30,"MemorySize":512,
    "Layers":[ref("PillowLayerArn")],"Environment":{"Variables":{
        "SOURCE_BUCKET":bucket_name("originals"),"DESTINATION_BUCKET":bucket_name("thumbnails")}},
    "Code":{"ZipFile":(ROOT/"src/resize_image.py").read_text()}}}
r["WorkflowRole"]=role("states.amazonaws.com",[statement("lambda:InvokeFunction",arn("Resize"))])
definition={"Comment":"Resize an image, check success, and end explicitly.","StartAt":"ResizeImage","TimeoutSeconds":120,"States":{
    "ResizeImage":{"Type":"Task","Resource":arn("Resize"),"Retry":[{
        "ErrorEquals":["Lambda.ServiceException","Lambda.AWSLambdaException","Lambda.SdkClientException","Lambda.TooManyRequestsException"],
        "IntervalSeconds":2,"MaxAttempts":3,"BackoffRate":2}],
        "Catch":[{"ErrorEquals":["States.ALL"],"ResultPath":"$.error","Next":"ProcessingFailed"}],"Next":"ResizeSuccessful"},
    "ResizeSuccessful":{"Type":"Choice","Choices":[{"Variable":"$.success","BooleanEquals":True,"Next":"ProcessingSucceeded"}],"Default":"ProcessingFailed"},
    "ProcessingSucceeded":{"Type":"Succeed"},"ProcessingFailed":{"Type":"Fail","Error":"ImageProcessingFailed","Cause":"The image could not be resized. Inspect the Task output and CloudWatch logs."}}}
r["Workflow"]={"Type":"AWS::StepFunctions::StateMachine","Properties":{
    "StateMachineName":sub("${AWS::StackName}-workflow"),"StateMachineType":"STANDARD",
    "RoleArn":arn("WorkflowRole"),"Definition":definition}}
r["StarterRole"]=role("lambda.amazonaws.com",[statement("states:StartExecution",ref("Workflow")),log_policy("starter")])
r["Starter"]={"Type":"AWS::Lambda::Function","DependsOn":"StarterLogs","Properties":{
    "FunctionName":sub("${AWS::StackName}-starter"),"Runtime":"python3.12","Handler":"index.lambda_handler",
    "Role":arn("StarterRole"),"Timeout":15,"MemorySize":128,"Environment":{"Variables":{
        "SOURCE_BUCKET":bucket_name("originals"),"STATE_MACHINE_ARN":ref("Workflow")}},
    "Code":{"ZipFile":(ROOT/"src/start_from_s3.py").read_text()}}}
r["AllowS3Invoke"]={"Type":"AWS::Lambda::Permission","Properties":{
    "FunctionName":ref("Starter"),"Action":"lambda:InvokeFunction","Principal":"s3.amazonaws.com",
    "SourceAccount":ref("AWS::AccountId"),"SourceArn":bucket_arn("originals")}}
for name,kind in [("OriginalsBucket","originals"),("ThumbnailsBucket","thumbnails")]:
    props={"BucketName":bucket_name(kind),"PublicAccessBlockConfiguration":{
        "BlockPublicAcls":True,"BlockPublicPolicy":True,"IgnorePublicAcls":True,"RestrictPublicBuckets":True},
        "BucketEncryption":{"ServerSideEncryptionConfiguration":[{"ServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}}
    item={"Type":"AWS::S3::Bucket","DeletionPolicy":"Retain","UpdateReplacePolicy":"Retain","Properties":props}
    if kind=="originals":
        props["VersioningConfiguration"]={"Status":"Enabled"}
        props["NotificationConfiguration"]={"LambdaConfigurations":[{"Event":"s3:ObjectCreated:*","Function":arn("Starter")}]}
        item["DependsOn"]=["AllowS3Invoke","ThumbnailsBucket"]
    r[name]=item
r["ApiRole"]=role("apigateway.amazonaws.com",[statement("states:StartExecution",ref("Workflow"))])
r["Api"]={"Type":"AWS::ApiGateway::RestApi","Properties":{"Name":sub("${AWS::StackName}-api"),"EndpointConfiguration":{"Types":["REGIONAL"]}}}
r["ProcessResource"]={"Type":"AWS::ApiGateway::Resource","Properties":{"RestApiId":ref("Api"),"ParentId":{"Fn::GetAtt":["Api","RootResourceId"]},"PathPart":"process"}}
r["ProcessMethod"]={"Type":"AWS::ApiGateway::Method","Properties":{
    "RestApiId":ref("Api"),"ResourceId":ref("ProcessResource"),"HttpMethod":"POST","AuthorizationType":"AWS_IAM",
    "Integration":{"Type":"AWS","IntegrationHttpMethod":"POST","Credentials":arn("ApiRole"),
        "Uri":sub("arn:${AWS::Partition}:apigateway:${AWS::Region}:states:action/StartExecution"),
        "PassthroughBehavior":"NEVER","RequestTemplates":{"application/json":sub('{"input": "$util.escapeJavaScript($input.json(\'$\')).replaceAll("\\\\\'", "\'")", "stateMachineArn": "${Workflow}"}')},
        "IntegrationResponses":[{"StatusCode":"200","SelectionPattern":"","ResponseTemplates":{"application/json":"$input.json('$')"}}]},
    "MethodResponses":[{"StatusCode":"200"}]}}
r["ApiDeployment"]={"Type":"AWS::ApiGateway::Deployment","DependsOn":"ProcessMethod","Properties":{"RestApiId":ref("Api")}}
r["ApiStage"]={"Type":"AWS::ApiGateway::Stage","Properties":{"RestApiId":ref("Api"),"DeploymentId":ref("ApiDeployment"),"StageName":"demo","MethodSettings":[{"ResourcePath":"/*","HttpMethod":"*","ThrottlingRateLimit":2,"ThrottlingBurstLimit":4}]}}
t={"AWSTemplateFormatVersion":"2010-09-09","Description":"COMP 200 serverless image processing capstone",
    "Parameters":{"PillowLayerArn":{"Type":"String","Description":"Python 3.12 x86_64 Linux Pillow layer version ARN","AllowedPattern":"arn:[^:]+:lambda:[^:]+:[0-9]{12}:layer:[^:]+:[0-9]+"}},
    "Resources":r,"Outputs":{
        "OriginalsBucket":{"Value":ref("OriginalsBucket")},"ThumbnailsBucket":{"Value":ref("ThumbnailsBucket")},
        "StateMachineArn":{"Value":ref("Workflow")},
        "ApiUrl":{"Value":sub("https://${Api}.execute-api.${AWS::Region}.${AWS::URLSuffix}/demo/process")}}}
(ROOT/"infrastructure/template.json").parent.mkdir(exist_ok=True)
(ROOT/"infrastructure/template.json").write_text(json.dumps(t,indent=2))
# Portable ASL example for the GitHub source submission.
portable=json.loads(json.dumps(definition).replace(json.dumps(arn("Resize")),json.dumps("${ResizeFunctionArn}")))
(ROOT/"infrastructure/state-machine.asl.json").write_text(json.dumps(portable,indent=2))
print("Generated CloudFormation and ASL files")
