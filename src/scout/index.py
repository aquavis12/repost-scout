import json, os, re, urllib.request, urllib.parse, datetime, boto3

BR = boto3.client("bedrock-runtime")
SNS = boto3.client("sns")
DDB = boto3.client("dynamodb")
UA = {"User-Agent": "Mozilla/5.0 (rePostScout personal agent)"}
MODEL = os.environ.get("MODEL_ID", "amazon.nova-lite-v1:0")

def get_questions(topic, limit=6):
    url = ("https://repost.aws/questions?view=unanswered&sort=recent&search="
           + urllib.parse.quote(topic))
    try:
        req = urllib.request.Request(url, headers=UA)
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"fetch failed for {topic}: {e}")
        return []
    links = re.findall(r'href="(/questions/(QU[\w-]+)/([\w-]+))"', html)
    seen, out = set(), []
    for path, qid, slug in links:
        if qid in seen:
            continue
        seen.add(qid)
        title = slug.replace("-", " ").strip().capitalize()
        out.append({"topic": topic, "title": title,
                    "url": "https://repost.aws" + path})
        if len(out) >= limit:
            break
    return out

def draft_brief(cands):
    listing = "\n".join(f"{i+1}. [{c['topic']}] {c['title']} — {c['url']}"
                        for i, c in enumerate(cands))
    prompt = f"""You are re:Post Scout, a daily agent for Vishnu, an AWS consultant
(AWS Community Builder). His strong lanes: Amazon Bedrock (KBs, agents),
ECS/Fargate ops and debugging, cost optimization (Trusted Advisor, Cost
Optimization Hub), CloudFormation, serverless.

Below are fresh UNANSWERED re:Post questions found today:
{listing}

Do this:
1. Pick the 3 questions Vishnu is best placed to answer from hands-on
   experience. Skip vague, account-specific, or billing-support posts.
2. For each pick, write:
   - WHY IT'S A FIT (1 line)
   - ANSWER OUTLINE: 3-5 bullets he can expand into an answer. Direct,
     experience-led voice. Short sentences. Concrete steps, exact console
     paths or CLI where useful. If something is uncertain, say "verify X"
     rather than inventing it. No fluff, no "great question".
3. End with a one-line "skip list" naming what you rejected and why.

Plain text only. Keep the whole brief under 450 words."""
    r = BR.converse(modelId=MODEL,
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                    inferenceConfig={"maxTokens": 1200, "temperature": 0.4})
    return r["output"]["message"]["content"][0]["text"]

def handler(event, context):
    topics = [t.strip() for t in os.environ["TOPICS"].split(",") if t.strip()]
    cands = []
    for t in topics:
        cands += get_questions(t)
    print(f"found {len(cands)} candidates")
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date().isoformat()
    if not cands:
        body = ("re:Post Scout ran but found no unanswered questions today "
                "(or page parsing broke - check the logs).")
    else:
        body = draft_brief(cands)
        body += "\n\n---\nAll candidates found today:\n" + "\n".join(
            f"- {c['title']}\n  {c['url']}" for c in cands)
    DDB.put_item(TableName=os.environ["TABLE"], Item={
        "run_date": {"S": today},
        "run_at_utc": {"S": now.isoformat(timespec="seconds")},
        "candidates": {"N": str(len(cands))},
        "brief": {"S": body[:35000]}})
    SNS.publish(
        TopicArn=os.environ["TOPIC_ARN"],
        Subject=f"re:Post Scout brief - {today}",
        Message=body)
    return {"candidates": len(cands)}
