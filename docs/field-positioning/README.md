# Field positioning

How this repository maps to the conversations a solution engineer actually has,
and — more usefully — where it should **not** be used.

## The three motions

| Motion | The question it answers | What this repository shows |
|---|---|---|
| **AI Apps** | How do we build an AI capability people can trust? | Contracts, retrieval, reasoning, evaluation, the demo UI |
| **Data** | Where does the evidence come from, and who may see it? | Entitlement-aware retrieval, classification, freshness, citations, audit |
| **Infrastructure** | How does this run safely, observably and within budget? | Bicep, managed identity, private networking, AI Gateway, cost attribution |

Most stalled AI programs have one of the three and are missing the other two.

## Conversations this supports

### "We built an agent and it works in the demo but we can't ship it"

The most common one. Usually the blocker is not the model — it is that nobody
can answer *who authorised that action*, *what evidence was it based on*, or
*what will it do next time*.

Show `major-defect`, then the audit receipt. The receipt binds the prediction
id, the policy decision id, the approval id and the action receipt id in one
verifiable chain. Then show `reap ready` failing its own gate, and say plainly
that this repository is not shippable either — and here is the list of what is
missing.

### "Our security team won't approve it"

Ask which control they are worried about. Then show the test.

The value here is not that the controls exist. It is that they are **enforced by
tests that fail the build** — `test_sole_writer.py` reads the import graph;
`test_plane_boundaries.py` fails if reasoning can reach a connector. A security
reviewer can read `SECURITY.md`, run `make check`, and see the controls hold.

Be equally direct about what is unmitigated: no authentication, no policy
signing, no durable approval store.

### "Frontier models are too expensive"

Show the routing decision with its **excluded candidates**. Show
`frontier_calls_avoided`. Show cost per completed task.

Then say what the numbers are: units from a mock reasoner, and no price, because
the repository does not know their rate card. The method transfers; the figures
do not.

### "How do we know it's working in production?"

Six KQL queries, an alert that fires on a write without an approval, and the
evaluation gate running against sampled live traffic — with the caveat that
continuous evaluation is designed and not built, and that none of the queries
has ever run against a real workspace.

### "Should we use an agent framework?"

Sometimes yes. [ADR-0002](../adr/0002-explicit-workflow-rather-than-agent-first.md)
states when: when the steps genuinely vary per request. This repository
deliberately does not demonstrate agent frameworks well, and should not be used
to argue against them.

## Where this does not apply

Being wrong about fit costs more than being unprepared.

| Situation | Why not |
|---|---|
| Consumer-facing chat with no write path | The governance spine is overhead. The retrieval and evaluation patterns still apply |
| Genuinely exploratory research | Determinism and approval gates are the wrong shape for a notebook |
| Truly dynamic workflows | Twelve fixed steps become a growing conditional. Use the agent adapter, or an agent framework |
| Terraform-standardised customers | Bicep only. They get a reference to translate, not a template to run |
| Sub-10ms decisioning | Even the local path spends milliseconds on retrieval and reasoning |
| Copilot Studio front-door scenarios | See `foundry-copilot-hr-policy-knowledge` and `warehouse-replenishment-ai-demo` |

## Related repositories

| Repository | Start there when |
|---|---|
| [foundry-workload-studio](https://github.com/honestypugh2/foundry-workload-studio) | Multiple workloads on one governed platform |
| [warehouse-replenishment-ai-demo](https://github.com/honestypugh2/warehouse-replenishment-ai-demo) | Copilot Studio + Foundry + D365 with human approval |
| [foundry-copilot-hr-policy-knowledge](https://github.com/honestypugh2/foundry-copilot-hr-policy-knowledge) | Choosing between retrieval patterns |
| [wordpress-chatbot](https://github.com/honestypugh2/wordpress-chatbot) | Per-user cost attribution through the AI Gateway |

See [reuse-and-attribution.md](../architecture/reuse-and-attribution.md).

## What not to say

- ❌ "This is production-ready." It is not, and `IMPLEMENTATION_STATUS.md` lists why.
- ❌ "The model is 94% accurate." There is no model. The mock is a hash.
- ❌ "This costs $X per transaction." No price appears anywhere in the repository.
- ❌ "READY AI is Microsoft guidance." It is an original field framework.
- ❌ "This has been deployed." Nothing has been deployed to any subscription.

The credibility of everything else depends on not saying these.
