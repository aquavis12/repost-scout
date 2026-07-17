# re:Post Scout

**An agent that runs while you sleep.** Every morning at 07:00 IST it searches AWS re:Post for fresh unanswered questions in my lanes, has Amazon Bedrock (Nova Lite) pick the three I can genuinely answer, drafts an answer outline for each in my voice, emails me the brief — and archives every run to a public log.

Built for the AWS Builder Center **Weekend Agent Challenge** (July 17–20, 2026).

📄 Challenge article: _[link once published]_
🌅 Live run log: _[Amplify URL once deployed]_

## Why

I'm an AWS Community Builder and I try to answer questions on re:Post. "Try" is the honest word — some weeks five, some weeks zero, depending on whether I remember to go looking. Scout removes the remembering. I read one email over coffee, spend 15 minutes polishing the best outline, and post.

## Architecture

```
EventBridge Scheduler ── cron(30 1 * * ? *) = 07:00 IST daily
        │
        ▼
  Lambda "repost-scout" (Python 3.12, code inline in CloudFormation)
        │  1. GET repost.aws/questions?view=unanswered&sort=recent&search=<topic>
        │  2. extract question links (regex on /questions/QU.../slug)
        │  3. one Bedrock Converse call: rank all candidates, draft top-3 outlines
        │
        ├──▶ Amazon SNS ──▶ email brief to my inbox
        └──▶ DynamoDB "repost-scout-briefs" ── one item per morning
                    │
                    ▼
        Lambda "repost-scout-archive" + Function URL (read-only, CORS)
                    │
                    ▼
        frontend/index.html ── static SPA on Amplify Hosting
```

Six services, one CloudFormation template, no API Gateway (a Lambda Function URL is enough for a read-only endpoint). Function code ships via **Lambda self-managed S3 code storage** (`S3ObjectStorageMode: REFERENCE`, launched July 2026) — Lambda reads the zips straight from a versioned bucket in this account, no Lambda-managed copy, no code storage quota used.

## Repo layout

```
template.yaml        # the entire backend — deploy this
src/scout/index.py   # the agent: fetch re:Post -> Bedrock -> SNS + DynamoDB
src/archive/index.py # read-only archive endpoint behind a Function URL
frontend/index.html  # the run-log SPA — host on Amplify (or any static host)
scripts/deploy.sh    # bootstrap bucket + upload + deploy + seed, one command
docs/                # challenge article draft + screenshots
```

## Built on a week-old launch

The functions started as inline `ZipFile` code in the template — until the scout hit 3,527 of the 4,096-character inline limit and the roadmap (dedupe, better parsing) clearly wouldn't fit. Instead of pivoting to SAM packaging, this repo uses [Lambda self-managed S3 code storage](https://aws.amazon.com/about-aws/whats-new/2026/07/lambda-self-managed-code-storage/), announced days before the challenge: the deploy script uploads zips to a **versioned** bucket (versioning is required — Lambda pins the exact object version), grants `lambda.amazonaws.com` `s3:GetObject`/`s3:GetObjectVersion` scoped with an `aws:SourceAccount` condition, and the template sets `S3ObjectStorageMode: REFERENCE`. The bucket stays the single source of truth; every deploy is just a new object version.

## Deploy

Prereqs: AWS CLI configured, us-east-1 (or any Bedrock region), Nova Lite model access enabled in the Bedrock console (Model access → Amazon → Nova Lite).

```bash
./scripts/deploy.sh you@example.com
```

The script bootstraps the versioned artifact bucket with the Lambda-principal bucket policy, zips `src/`, uploads (capturing S3 VersionIds), and deploys the stack with those versions pinned. Code change? Re-run it — new object versions, stack update, done.

Then:

1. **Confirm the SNS subscription** — one email, one click. That's the entire email setup (no SES identities, no sandbox).
2. **Seed the log** — invoke once so the archive isn't empty:
   ```bash
   aws lambda invoke --function-name repost-scout --region us-east-1 /tmp/out.json && cat /tmp/out.json
   ```
3. **Wire the frontend** — copy the `ArchiveApiUrl` stack output into `API_URL` at the top of `frontend/index.html`.
4. **Host it** — Amplify Console → New app → *Deploy without Git* → drag a zip of `frontend/`. Live in ~1 minute.

## Parameters

| Parameter | Default | Notes |
|---|---|---|
| `RecipientEmail` | — | Where the daily brief lands |
| `Topics` | `bedrock,fargate,cost optimization,cloudformation` | Comma-separated re:Post search terms — set your own lanes |
| `ScheduleExpression` | `cron(30 1 * * ? *)` | 01:30 UTC = 07:00 IST |
| `ModelId` | `amazon.nova-lite-v1:0` | Any Bedrock model supporting Converse |

The agent prompt (inside `template.yaml`, in the scout Lambda) is opinionated on purpose: it knows my lanes, skips vague and billing-support posts, and is told to write "verify X" instead of inventing details. Edit it to sound like you.

## Evidence it runs without you

- The live run log — every entry stamped with its 07:00 IST run time
- EventBridge Scheduler console showing `repost-scout-daily` and its next run
- CloudWatch Logs for the *scheduled* invocations (not just the manual seed)

## Known limitations (v1)

- **No official re:Post API.** The Lambda parses the public questions page; if AWS changes the URL structure or markup, the regex in `get_questions()` needs updating. Question titles are derived from URL slugs, so they lose original casing.
- **No dedupe across days.** A still-unanswered question can reappear tomorrow. The DynamoDB table makes a seen-set an easy v2.
- **Archive endpoint is public read-only.** It serves only what the agent wrote. If that bothers you, put CloudFront + WAF in front or switch the Function URL to `AWS_IAM`.

## Cost

Scheduler free at this volume · Lambda one invocation/day, rounds to zero · Nova Lite a few thousand tokens/day (low single-digit cents/month) · SNS one email/day · DynamoDB on-demand, one write/day · Amplify Hosting free tier. Effectively free.

## License

MIT
