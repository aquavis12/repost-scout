#!/usr/bin/env bash
# re:Post Scout — bootstrap artifact bucket, upload code, deploy, seed.
# Uses Lambda self-managed S3 code storage (S3ObjectStorageMode=REFERENCE, July 2026).
# Usage: ./scripts/deploy.sh you@example.com [region]
set -euo pipefail

EMAIL="${1:?Usage: ./scripts/deploy.sh you@example.com [region]}"
REGION="${2:-us-east-1}"
STACK="repost-scout"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="repost-scout-artifacts-${ACCOUNT}-${REGION}"

echo "==> Bootstrapping artifact bucket s3://$BUCKET ..."
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
  fi
fi
# Versioning is REQUIRED for self-managed code storage - Lambda tracks object versions
aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

# Grant the Lambda service principal read access, scoped to this account
aws s3api put-bucket-policy --bucket "$BUCKET" --policy "$(cat <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "LambdaSelfManagedCodeStorage",
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": ["s3:GetObject", "s3:GetObjectVersion"],
    "Resource": "arn:aws:s3:::${BUCKET}/*",
    "Condition": {"StringEquals": {"aws:SourceAccount": "${ACCOUNT}"}}
  }]
}
POLICY
)"

echo "==> Packaging and uploading function code ..."
upload() { # $1 = src dir name, $2 = s3 key -> echoes VersionId
  local tmp; tmp=$(mktemp -d)
  (cd "$ROOT/src/$1" && zip -qr "$tmp/$2" .)
  aws s3api put-object --bucket "$BUCKET" --key "$2" \
    --body "$tmp/$2" --query VersionId --output text
  rm -rf "$tmp"
}
SCOUT_VER=$(upload scout scout.zip)
ARCHIVE_VER=$(upload archive archive.zip)
echo "    scout.zip   version $SCOUT_VER"
echo "    archive.zip version $ARCHIVE_VER"

echo "==> Deploying stack '$STACK' to $REGION ..."
aws cloudformation deploy \
  --template-file "$ROOT/template.yaml" \
  --stack-name "$STACK" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION" \
  --parameter-overrides \
      RecipientEmail="$EMAIL" \
      ArtifactBucket="$BUCKET" \
      ScoutObjectVersion="$SCOUT_VER" \
      ArchiveObjectVersion="$ARCHIVE_VER"

echo "==> Check your inbox and CONFIRM the SNS subscription (one click)."
read -rp "Press Enter once confirmed to seed the first run..."

echo "==> Invoking repost-scout once to seed the archive ..."
aws lambda invoke --function-name repost-scout --region "$REGION" /tmp/scout-out.json >/dev/null
cat /tmp/scout-out.json; echo

ARCHIVE_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ArchiveApiUrl'].OutputValue" --output text)

echo
echo "==> Done. Next steps:"
echo "    1. Put this in API_URL at the top of frontend/index.html:"
echo "       $ARCHIVE_URL"
echo "    2. Zip frontend/ and drag into Amplify Console (Deploy without Git)."
echo "    3. The daily schedule fires at 07:00 IST. Check your inbox tomorrow."
echo
echo "    To ship a code change: re-run this script - it uploads new object"
echo "    versions and updates the stack. Lambda references your bucket"
echo "    directly (REFERENCE mode); no copy step, no storage quota used."
