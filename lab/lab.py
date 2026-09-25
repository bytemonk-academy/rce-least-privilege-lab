#!/usr/bin/env python3
"""
ByteMonk least-privilege lab CLI.

Creates the demo buckets and the application's IAM role, swaps the role between
the "broad" and "restricted" policies, and runs the same two S3 reads with the
role's temporary credentials so you can see which ones succeed.

It never prints credentials and it never touches anything it did not create.

Targets
  local  An AWS API emulator (moto) running in Docker. Free, no AWS account.
  aws    A real AWS account. Use a dedicated sandbox account.

Usage
  python lab.py setup
  python lab.py check-access [--expect broad|restricted]
  python lab.py use-policy restricted
  python lab.py status
  python lab.py aws s3 ls                       (AWS CLI as the lab operator)
  python lab.py aws --as-app s3 ls s3://<bucket> (AWS CLI as the app role)
  python lab.py cleanup
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
IAM_DIR = Path(os.environ.get("LAB_IAM_DIR", ROOT / "infra" / "iam"))
FIXTURES_DIR = Path(os.environ.get("LAB_FIXTURES_DIR", ROOT / "fixtures"))
STATE_DIR = Path(os.environ.get("LAB_STATE_DIR", ROOT / ".lab"))

TARGET = os.environ.get("LAB_TARGET", "local")
ENDPOINT = os.environ.get("LAB_AWS_ENDPOINT", "http://localhost:5050")
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
PREFIX = os.environ.get("LAB_NAME_PREFIX", "rce-lab")

ROLE_NAME = f"{PREFIX}-recruit-app-role"
INSTANCE_PROFILE = f"{PREFIX}-recruit-app-profile"
POLICY_NAME = "recruit-app-s3-access"
OPERATOR_USER = f"{PREFIX}-operator"  # local target only

RESUME_KEY = "resumes/fixtures/jane-candidate-resume.pdf"
ARCHIVE_KEY = "employees/employee-records-SYNTHETIC.csv"
FIXTURE_FILES = {
    "resume": FIXTURES_DIR / "resumes" / "jane-candidate-resume.pdf",
    "archive": FIXTURES_DIR / "employee-archive" / "employee-records-SYNTHETIC.csv",
}

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


GREEN, RED, DIM, BOLD = "32", "31", "2", "1"


# --------------------------------------------------------------------------- #
# State and clients
# --------------------------------------------------------------------------- #

def state_path() -> Path:
    return STATE_DIR / f"state-{TARGET}.json"


def load_state() -> dict:
    path = state_path()
    if not path.exists():
        sys.exit(f"No lab state for target '{TARGET}'. Run: python lab.py setup")
    return json.loads(path.read_text())


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path().write_text(json.dumps(state, indent=2) + "\n")


def is_local() -> bool:
    if TARGET not in ("local", "aws"):
        sys.exit(f"LAB_TARGET must be 'local' or 'aws', got '{TARGET}'")
    return TARGET == "local"


def operator_session(state: dict | None = None) -> boto3.Session:
    """The identity that manages the lab (you, the operator)."""
    if is_local():
        creds = (state or {}).get("operator", {})
        return boto3.Session(
            aws_access_key_id=creds.get("access_key_id", "bootstrap"),
            aws_secret_access_key=creds.get("secret_access_key", "bootstrap"),
            region_name=REGION,
        )
    return boto3.Session(region_name=REGION)


def client(session: boto3.Session, service: str):
    kwargs = {"config": Config(retries={"max_attempts": 2, "mode": "standard"})}
    if is_local():
        kwargs["endpoint_url"] = ENDPOINT
    return session.client(service, **kwargs)


def moto_api(path: str, body: str = "") -> None:
    req = urllib.request.Request(f"{ENDPOINT}/moto-api/{path}", data=body.encode(), method="POST",
                                 headers={"Content-Type": "text/plain"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def wait_for_endpoint() -> None:
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{ENDPOINT}/moto-api/", timeout=2).read()
            return
        except Exception:
            time.sleep(1)
    sys.exit(f"The local AWS emulator is not reachable at {ENDPOINT}. Is 'docker compose up' running?")


def wait_for_iam() -> None:
    """IAM is eventually consistent: new roles and policy changes take a few seconds to apply."""
    seconds = int(os.environ.get("LAB_IAM_WAIT", "15"))
    if seconds > 0:
        print(f"Waiting {seconds} seconds for the IAM change to propagate...")
        time.sleep(seconds)


def render(path: Path, values: dict) -> str:
    text = path.read_text()
    for key, value in values.items():
        text = text.replace("${" + key + "}", value)
    return text


def policy_document(name: str, state: dict) -> str:
    path = IAM_DIR / f"{name}.json"
    if not path.exists():
        sys.exit(f"Unknown policy '{name}'. Expected {path}")
    return render(path, {"RESUME_BUCKET": state["resume_bucket"], "ARCHIVE_BUCKET": state["archive_bucket"]})


def ignore(codes: tuple[str, ...], fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ClientError as err:
        if err.response["Error"]["Code"] in codes:
            return None
        raise


# --------------------------------------------------------------------------- #
# setup
# --------------------------------------------------------------------------- #

def already_set_up() -> bool:
    """True when the local emulator still holds the lab created by a previous setup."""
    path = state_path()
    if not path.exists():
        return False
    state = json.loads(path.read_text())
    try:
        client(operator_session(state), "iam").get_role(RoleName=state["role_name"])
        return (STATE_DIR / "app.properties").exists()
    except Exception:
        return False


def cmd_setup(args) -> None:
    if is_local():
        wait_for_endpoint()
        if args.if_needed and already_set_up():
            print("Lab already set up in the local emulator. Nothing to do.")
            return
        # Turn IAM enforcement off while we bootstrap, then back on at the end.
        # moto keeps everything in memory, so we always start from a clean slate.
        moto_api("reset")
        moto_api("reset-auth", "inf")
        state: dict = {"target": "local"}
        session = operator_session(state)
        account = "123456789012"  # moto's default account
    else:
        session = operator_session()
        account = client(session, "sts").get_caller_identity()["Account"]
        state = {"target": "aws"}

    state.update(
        account_id=account,
        region=REGION,
        resume_bucket=f"{PREFIX}-resumes-{account}-{REGION}",
        archive_bucket=f"{PREFIX}-hr-archive-{account}-{REGION}",
        role_name=ROLE_NAME,
        role_arn=f"arn:aws:iam::{account}:role/{ROLE_NAME}",
        instance_profile=INSTANCE_PROFILE,
        resume_key=RESUME_KEY,
        archive_key=ARCHIVE_KEY,
    )

    s3 = client(session, "s3")
    iam = client(session, "iam")

    print(color(f"Setting up the lab on target '{TARGET}' in {REGION}", BOLD))

    for bucket in (state["resume_bucket"], state["archive_bucket"]):
        create_args = {"Bucket": bucket}
        if REGION != "us-east-1":
            create_args["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
        ignore(("BucketAlreadyOwnedByYou",), s3.create_bucket, **create_args)
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": "project", "Value": PREFIX}]})
        print(f"  bucket   {bucket} (private)")

    s3.put_object(Bucket=state["resume_bucket"], Key=RESUME_KEY,
                  Body=FIXTURE_FILES["resume"].read_bytes(), ContentType="application/pdf")
    s3.put_object(Bucket=state["archive_bucket"], Key=ARCHIVE_KEY,
                  Body=FIXTURE_FILES["archive"].read_bytes(), ContentType="text/csv")
    print(f"  fixture  s3://{state['resume_bucket']}/{RESUME_KEY}")
    print(f"  fixture  s3://{state['archive_bucket']}/{ARCHIVE_KEY}")

    if is_local():
        # A stand-in for "you": an operator user that can manage the lab and assume the app role.
        user_arn = iam.create_user(UserName=OPERATOR_USER)["User"]["Arn"]
        iam.put_user_policy(UserName=OPERATOR_USER, PolicyName="lab-operator", PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}],
        }))
        key = iam.create_access_key(UserName=OPERATOR_USER)["AccessKey"]
        state["operator"] = {"access_key_id": key["AccessKeyId"], "secret_access_key": key["SecretAccessKey"]}
        operator_principal = user_arn
    else:
        # Any identity in this account that is allowed sts:AssumeRole (for example, your admin user).
        operator_principal = f"arn:aws:iam::{account}:root"

    trust = render(IAM_DIR / "trust-policy.json", {"OPERATOR_PRINCIPAL": operator_principal})
    if ignore(("EntityAlreadyExists",), iam.create_role, RoleName=ROLE_NAME, AssumeRolePolicyDocument=trust,
              Description="Role used by the demo recruitment app", MaxSessionDuration=3600,
              Tags=[{"Key": "project", "Value": PREFIX}]) is None:
        iam.update_assume_role_policy(RoleName=ROLE_NAME, PolicyDocument=trust)
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName=POLICY_NAME,
                        PolicyDocument=policy_document(args.policy, state))
    state["policy"] = args.policy
    print(f"  role     {state['role_arn']}")
    print(f"  policy   {args.policy}.json attached as '{POLICY_NAME}'")

    ignore(("EntityAlreadyExists",), iam.create_instance_profile, InstanceProfileName=INSTANCE_PROFILE)
    ignore(("LimitExceeded", "EntityAlreadyExists"), iam.add_role_to_instance_profile,
           InstanceProfileName=INSTANCE_PROFILE, RoleName=ROLE_NAME)
    print(f"  profile  {INSTANCE_PROFILE} (attach this to an EC2 instance to run the app there)")

    if is_local():
        write_app_properties(state)
        moto_api("reset-auth", "0")  # From here on, every request is checked against IAM policies.
        print("  auth     IAM enforcement ON in the local emulator")

    save_state(state)
    if not is_local():
        wait_for_iam()
    print(color("Setup complete. Next: run check-access", GREEN))


def write_app_properties(state: dict) -> None:
    """Credentials the local app uses to assume its role (local emulator keys only, never real ones)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated by lab/lab.py setup for the LOCAL emulator. Not real AWS credentials.",
        f"lab.aws.base-access-key-id={state['operator']['access_key_id']}",
        f"lab.aws.base-secret-access-key={state['operator']['secret_access_key']}",
        f"lab.aws.role-arn={state['role_arn']}",
        f"lab.storage.resume-bucket={state['resume_bucket']}",
        "",
    ]
    (STATE_DIR / "app.properties").write_text("\n".join(lines))


# --------------------------------------------------------------------------- #
# check-access
# --------------------------------------------------------------------------- #

def assume_app_role(state: dict, session_name: str = "check-access") -> boto3.Session:
    """Get fresh temporary credentials for the app role, like an EC2 instance profile would."""
    sts = client(operator_session(state), "sts")
    for attempt in range(5):
        try:
            creds = sts.assume_role(RoleArn=state["role_arn"], RoleSessionName=session_name,
                                    DurationSeconds=900)["Credentials"]
            break
        except ClientError as err:
            # A brand-new role can take a few seconds to become assumable on real AWS.
            if is_local() or err.response["Error"]["Code"] != "AccessDenied" or attempt == 4:
                raise
            time.sleep(3)
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=REGION,
    )


def try_read(s3, bucket: str, key: str) -> tuple[bool, str]:
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        return True, f"{len(body)} bytes"
    except ClientError as err:
        return False, err.response["Error"]["Code"]


def cmd_check_access(args) -> None:
    state = load_state()
    app = assume_app_role(state)
    identity = client(app, "sts").get_caller_identity()["Arn"]
    s3 = client(app, "s3")

    print(color("Code running with the recruitment app's identity", BOLD))
    print(f"  identity  {identity}")
    print(f"  policy    infra/iam/{state['policy']}.json")
    print(color("  No recruiter login and no controller checks: this calls S3 directly.", DIM))
    print()

    checks = [
        ("resume", "resume bucket", state["resume_bucket"], state["resume_key"]),
        ("archive", "employee archive", state["archive_bucket"], state["archive_key"]),
    ]
    results = {}
    for name, label, bucket, key in checks:
        ok, detail = try_read(s3, bucket, key)
        results[name] = ok
        verdict = color("ALLOWED", GREEN) if ok else color("DENIED ", RED)
        print(f"  {verdict}  GetObject {label:<17} {key:<45} {detail}")

    if args.expect:
        expected = {"broad": {"resume": True, "archive": True},
                    "restricted": {"resume": True, "archive": False}}[args.expect]
        print()
        if results == expected:
            print(color(f"Matches the expected result for '{args.expect}'.", GREEN))
        else:
            print(color(f"Does NOT match the expected result for '{args.expect}': {expected}", RED))
            sys.exit(1)


# --------------------------------------------------------------------------- #
# use-policy / status / cleanup
# --------------------------------------------------------------------------- #

def cmd_use_policy(args) -> None:
    state = load_state()
    iam = client(operator_session(state), "iam")
    iam.put_role_policy(RoleName=state["role_name"], PolicyName=POLICY_NAME,
                        PolicyDocument=policy_document(args.name, state))
    state["policy"] = args.name
    save_state(state)
    print(f"Attached {args.name}.json to {state['role_name']}.")
    if not is_local():
        # IAM is eventually consistent. Give the change a moment before testing.
        wait_for_iam()
    print("Next: run check-access again")


def cmd_aws(args) -> None:
    """Run the AWS CLI as the lab operator, or with --as-app, as the recruitment app's role."""
    state = load_state()
    env = dict(os.environ)
    if args.as_app:
        creds = assume_app_role(state, "aws-cli").get_credentials().get_frozen_credentials()
        env.update(AWS_ACCESS_KEY_ID=creds.access_key, AWS_SECRET_ACCESS_KEY=creds.secret_key,
                   AWS_SESSION_TOKEN=creds.token)
        env.pop("AWS_PROFILE", None)
        print(color(f"[running as {state['role_name']}]", DIM), file=sys.stderr)
    elif is_local():
        env.update(AWS_ACCESS_KEY_ID=state["operator"]["access_key_id"],
                   AWS_SECRET_ACCESS_KEY=state["operator"]["secret_access_key"])
        env.pop("AWS_SESSION_TOKEN", None)
        env.pop("AWS_PROFILE", None)
    if is_local():
        env["AWS_ENDPOINT_URL"] = ENDPOINT
    env.setdefault("AWS_DEFAULT_REGION", REGION)
    env.setdefault("AWS_PAGER", "")
    cli_args = args.aws_args[1:] if args.aws_args[:1] == ["--"] else args.aws_args
    if not cli_args:
        sys.exit("Usage: lab.py aws [--as-app] <aws cli arguments>, for example: lab.py aws s3 ls")
    try:
        os.execvpe("aws", ["aws", *cli_args], env)
    except FileNotFoundError:
        sys.exit("The AWS CLI is not installed. Use scripts/aws-local (it runs inside Docker) "
                 "or install it: pip install awscli")


def cmd_status(args) -> None:
    state = load_state()
    visible = {k: v for k, v in state.items() if k != "operator"}
    print(json.dumps(visible, indent=2))


def cmd_cleanup(args) -> None:
    path = state_path()
    if is_local():
        try:
            moto_api("reset-auth", "inf")
            moto_api("reset")
        except Exception:
            pass  # emulator already gone; nothing to clean up
        print("Local emulator reset.")
    elif path.exists():
        state = json.loads(path.read_text())
        session = operator_session()
        s3 = client(session, "s3")
        iam = client(session, "iam")
        for bucket in (state["resume_bucket"], state["archive_bucket"]):
            try:
                paginator = s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket):
                    objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                    if objects:
                        s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
                s3.delete_bucket(Bucket=bucket)
                print(f"Deleted bucket {bucket}")
            except ClientError as err:
                if err.response["Error"]["Code"] != "NoSuchBucket":
                    raise
        ignore(("NoSuchEntity",), iam.remove_role_from_instance_profile,
               InstanceProfileName=state["instance_profile"], RoleName=state["role_name"])
        ignore(("NoSuchEntity",), iam.delete_instance_profile, InstanceProfileName=state["instance_profile"])
        ignore(("NoSuchEntity",), iam.delete_role_policy, RoleName=state["role_name"], PolicyName=POLICY_NAME)
        ignore(("NoSuchEntity",), iam.delete_role, RoleName=state["role_name"])
        print(f"Deleted role {state['role_name']} and instance profile {state['instance_profile']}")
    for leftover in (path, STATE_DIR / "app.properties"):
        if leftover.exists() and (TARGET == "local" or leftover == path):
            leftover.unlink()
    print(color("Cleanup complete.", GREEN))


def main() -> None:
    global TARGET
    parser = argparse.ArgumentParser(description="ByteMonk least-privilege lab")
    parser.add_argument("--target", choices=["local", "aws"], help="override LAB_TARGET (default: local)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("setup", help="create buckets, fixtures and the app role")
    p.add_argument("--policy", default="broad", help="policy to start with (default: broad)")
    p.add_argument("--if-needed", action="store_true", help="local: skip if the emulator is already set up")
    p.set_defaults(fn=cmd_setup)

    p = sub.add_parser("check-access", help="run the two reads with the app role's credentials")
    p.add_argument("--expect", choices=["broad", "restricted"], help="exit non-zero if results differ")
    p.set_defaults(fn=cmd_check_access)

    p = sub.add_parser("use-policy", help="attach infra/iam/<name>.json to the app role")
    p.add_argument("name", help="broad or restricted")
    p.set_defaults(fn=cmd_use_policy)

    p = sub.add_parser("aws", help="run the AWS CLI against the lab (as operator, or --as-app)")
    p.add_argument("--as-app", action="store_true", help="use the app role's temporary credentials")
    p.add_argument("aws_args", nargs=argparse.REMAINDER, help="arguments for the aws command")
    p.set_defaults(fn=cmd_aws)

    sub.add_parser("status", help="show lab resources").set_defaults(fn=cmd_status)
    sub.add_parser("cleanup", help="delete everything the lab created").set_defaults(fn=cmd_cleanup)

    args = parser.parse_args()
    if args.target:
        TARGET = args.target
    try:
        args.fn(args)
    except ClientError as err:
        code = err.response["Error"]["Code"]
        sys.exit(f"AWS error ({code}): {err.response['Error'].get('Message', '')}")


if __name__ == "__main__":
    main()
