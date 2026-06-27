# Provenance Guard — System Specification & Plan

## Architecture
A content submission (`POST /submit`) accepts raw text and a `creator_id`, generates a unique tracking `content_id`, and routes the text sequentially through two distinct analysis engines: an LLM-based semantic evaluator via Groq and a local structural stylometric heuristic engine. The outputs from both signals are combined using an asymmetric weighted formula to produce an aggregate confidence score between 0.0 and 1.0. This score maps directly to a user-facing transparency label. Every single attribution decision is immediately written as a structured JSON object to an audit log database before the response is returned.

An appeal (`POST /appeal`) references an existing `content_id`, updates its lifecycle state to "under_review", and appends the creator's qualitative reasoning directly to the matching log entry.

### System Architecture Diagram
```text
[ Submission Flow ]
   User Text ──> POST /submit ──> Generate content_id
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
            [Signal 1: Groq LLM]                 [Signal 2: Heuristics]
          (Returns P(AI): 0.0-1.0)              (Returns P(AI): 0.0-1.0)
                    │                                     │
                    └──────────────────┬──────────────────┘
                                       ▼
                           [Weighted Confidence Score]
                                       │
                                       ▼
                           [Transparency Label Router]
                                       │
                                       ▼
                           [Write to Audit Log] ──> Return JSON Response

[ Appeal Flow ]
   Creator Reason ──> POST /appeal ──> Lookup content_id ──> Update Status to "under_review" ──> Update Log

You are completely right—my apologies! The code block cut off early and left out the rest of the specification. Let's fix that immediately so you have the entire document exactly as it needs to be.Here is the complete, uncut planning.md file from top to bottom.Markdown# Provenance Guard — System Specification & Plan

## Architecture
A content submission (`POST /submit`) accepts raw text and a `creator_id`, generates a unique tracking `content_id`, and routes the text sequentially through two distinct analysis engines: an LLM-based semantic evaluator via Groq and a local structural stylometric heuristic engine. The outputs from both signals are combined using an asymmetric weighted formula to produce an aggregate confidence score between 0.0 and 1.0. This score maps directly to a user-facing transparency label. Every single attribution decision is immediately written as a structured JSON object to an audit log database before the response is returned.

An appeal (`POST /appeal`) references an existing `content_id`, updates its lifecycle state to "under_review", and appends the creator's qualitative reasoning directly to the matching log entry.

### System Architecture Diagram
```text
[ Submission Flow ]
   User Text ──> POST /submit ──> Generate content_id
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
            [Signal 1: Groq LLM]                 [Signal 2: Heuristics]
          (Returns P(AI): 0.0-1.0)              (Returns P(AI): 0.0-1.0)
                    │                                     │
                    └──────────────────┬──────────────────┘
                                       ▼
                           [Weighted Confidence Score]
                                       │
                                       ▼
                           [Transparency Label Router]
                                       │
                                       ▼
                           [Write to Audit Log] ──> Return JSON Response

[ Appeal Flow ]
   Creator Reason ──> POST /appeal ──> Lookup content_id ──> Update Status to "under_review" ──> Update Log
```

## Detection Signals
To capture completely independent surface properties of the submitted text, the pipeline splits analysis into semantic and structural dimensions:

* **Signal 1: Groq LLM Semantic Profiler (llama-3.3-70b-versatile)**
    * _What it measures_: Captures semantic choices, holistic tone, overused AI transition words ("Furthermore," "It is important to note"), and unnaturally consistent rhythm.
    * _Why it differs_: LLMs optimize for the most probable next token, leading to highly standardized, cliché-ridden phrasing over long passages compared to natural human expression.
    * _Blind spot_: Highly formal, academic, or technical prose written by humans, which naturally shares a structured, objective cadence.

* **Signal 2: Stylometric Heuristic Engine (Pure Python)**
    * _What it measures_: Sentence Length Variance (SLV) and Type-Token Ratio (TTR) (vocabulary diversity).
    * _Why it differs_: Human writing is structurally dynamic, blending short, punchy fragments with long, complex sentences while varying word selection. AI text tends to cluster tightly around highly uniform sentence structures and safe, middle-tier vocabulary.
    * _Blind spot_: Highly structured human creative writing forms, such as fixed-meter poetry or repetitive flash fiction, which naturally compress stylistic variance.

## Signal Combination Formula
Because falsely accusing a human creator of using AI is a catastrophic platform failure mode, the formula leans heavily on the semantic model while utilizing the structural metrics as a calibrator:

$$Score = (0.65 \times S_{llm}) + (0.35 \times S_{heur})$$

## Uncertainty Representation
The final combined score determines the classification tier. To minimize false positives, the "Uncertain" buffer zone is intentionally wide and shifted toward higher scores:

* $0.00 \le Score < 0.40$: Likely Human
* $0.40 \le Score \le 0.75$: Uncertain / Mixed Signals
* $0.75 < Score \le 1.00$: Likely AI-Generated

## Transparency Label Design
The system will return the exact, plain-language copy to display directly to non-technical users:

* **High-Confidence Human ($Score < 0.40$)**:
"Verified Human Attribution — This content aligns consistently with human writing patterns and structural variance."
* **Uncertain ($0.40 \le Score \le 0.75$)**:
"Attribution Unverifiable — This text contains a mixture of stylistic markers. Content context cannot be definitively automated.
* **"High-Confidence AI ($Score > 0.75$)**:
"Automated Content Label — Our systems indicate a high probability that this text was generated using an AI model."

## Appeals Workflow & Edge Cases
* **Workflow**: Any creator whose content returns an AI or Uncertain label can submit a payload to `/appeal` containing the `content_id` and their text-based `creator_reasoning`. The storage system updates the entry status to `under_review`. An internal review queue exposes these rows sorted by oldest timestamp first, showing the original classification scores alongside the author's statement.
* **Anticipated Edge Case 1 (Non-Native Speakers)**: Authors writing in English as a second language may utilize highly structured, grammatically rigid sentence structures that lower structural variance, potentially triggering a false "Uncertain" flag.
* **Anticipated Edge Case 2 (Technical Documentation/Tutorials)**: Step-by-step guides inherently require uniform sentence lengths and repetitive vocabulary, which might trick the stylometric engine into flagging it as AI.

## AI Tool Plan
* **Submission Endpoint & First Signal (Milestone 3)**: Provide the Architecture and Detection Signals sections to the AI. Direct it to generate the base Flask app skeleton, a mockable audit logging engine, and the Groq LLM client connection that parses structured JSON out of the prompt response.
* **Second Signal & Confidence Scoring (Milestone 4 )**: Provide the Detection Signals and Uncertainty Representation criteria. Direct it to implement the native Python text-parsing utilities for SLV and TTR, followed by the combined weighting formula.
* **Production Layer (Milestone 5)**: Provide the Transparency Label Design and Appeals Workflow sections. Direct it to build out the endpoint route updates, the `POST /appeal` handler, and wire up `Flask-Limiter` with explicit memory-backed storage tracking.