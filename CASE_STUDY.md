# Case study: sorting bilingual support tickets so urgent ones come first

**Demo scenario. Puentara is a fictional company.** All tickets are synthetic. No real customers, results or clients are described here.

## The situation

Puentara is a money app for freelancers and small businesses in the US and Latin America. Customers write in English, in Spanish, and sometimes in both in the same message. Tickets come in through chat, email and a web form, and they all land in one queue.

## The problem

Nobody knows which ticket is urgent until someone reads it. So a customer whose card was just stolen waits in the same line as someone asking about support hours. A charge the customer doesn't recognize can sit for hours. When it's finally read, the money may already be gone.

Spanish tickets wait longer, because only some agents read Spanish. Each agent sorts tickets in their own way. And customers sometimes type their full card number or a one-time code into the ticket, which then gets copied into notes and spreadsheets.

My customer support experience, including work on a banking campaign, has shown me how much a slow response to a stolen card or compromised account can affect customers. Delays can increase frustration, generate repeat calls, and make resolution more difficult.

## The solution

The support lead exports the day's tickets to a CSV file and runs one command. They get:

- An **"URGENT - handle these first"** list at the top: stolen cards, possible account takeovers, and charges the customer doesn't recognize, in both languages.
- Every ticket tagged with a **category, urgency, language and queue**, so each team opens only its own work.
- Card numbers, CVVs and one-time codes **masked** before anyone else sees them.
- A short **"needs review"** list for tickets the tool wasn't sure about. Those go to a person instead of being guessed.
- The summary in **English or Spanish**, whichever the team prefers.

The tool never writes to customers. It only sorts. Anything about money, fraud, disputes or account access is marked for a person, every time.

## What was built

- A Python command-line tool that reads a helpdesk CSV export and writes a sorted CSV plus a summary.
- Keyword rules in English and Spanish for the clear cases, with a fixed escalation table.
- Claude (Anthropic's AI model) for the unclear tickets only. A demo mode uses hand-written sample answers, so it runs without an API key.
- Safety floors the AI can't override, and a review list for anything uncertain.
- An evaluation script and 199 automated tests that run offline.

## What the demo shows

All numbers below are from **sample data**: synthetic tickets generated from templates, run in demo mode. They come from `docs/demo_output.txt` in the repo.

**30 sample tickets, one run:**

- 8 marked urgent and placed at the top, all in the fraud and security queue (5 of them in Spanish).
- 18 decided by the rules, 10 by the AI step (hand-written sample answers in demo mode, not a real model), and 2 sent to review.
- The 2 review cases: a ticket in French, and a deliberately broken AI answer. Both went to a person instead of being guessed.
- 3 tickets had card numbers or codes masked. In one Spanish ticket, the customer typed a full card number and CVV. The output shows `[CARD NUMBER MASKED]` and `[CODE MASKED]` instead.
- 22 of 30 marked as needing a human, because most were about money, cards or account access.

**Evaluation on 150 labeled test tickets (rules layer only):**

- The rules decided 132 of 150 tickets (88.0%). The rest would go to the AI.
- Category and urgency were right on all 132 rule-decided tickets.
- The rules alone caught 38 of 39 urgent tickets (97.4%). The one miss was a Spanish ticket with a typo ("trajeta" instead of "tarjeta"). I left it in as an honest miss.

**What these numbers mean, and what they don't.** The test tickets are template-generated synthetic data. They come from the same templates the rules were written against, just with a different random seed. That is why the rule-decided accuracy is 100%. These numbers show the tool works on this set. They are not real-world accuracy. Real tickets have more typos, slang and mixed topics. These are also rules-layer numbers only: the AI layer has not been scored yet, because demo mode uses hand-written answers. I'll run the full pipeline with a real key later.

## How I'd adapt it for a real client

1. **Your export.** Share a small, sanitized sample CSV from Zendesk, Freshdesk, or your helpdesk, with personal and confidential information removed. I'll map any column names that differ.
2. **Your categories and queues.** I'd change the category list, the queues and the escalation table to match how your team works.
3. **Your customers' words.** I'd tune the English and Spanish rules on a sample of your real tickets (with personal data removed), then measure accuracy on tickets the rules have never seen. That gives you an honest number for your data.
4. **Your safety rules.** We'd agree on what counts as urgent and what always goes to a person, and I'd add tests for each rule.
5. **Later, if you want it:** tag tickets as they arrive through your helpdesk's API, instead of working from an export.

Send me a small sample of sanitized, non-sensitive tickets, and I'll show you how this would sort them.
