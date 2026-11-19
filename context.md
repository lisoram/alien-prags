# Multi-Domain Research Assistant: Context File for AI Assistants

**Read this whole file before doing anything.** It is the handoff
document for any AI assistant (Antigravity, Claude Code, or any other)
working on this project. If you are a new assistant picking up work,
this file plus `docs/` (especially `docs/module_specs.pdf`) should be
enough to understand the project and continue safely.

------------------------------------------------------------------------

## 1. Working Rules (most important section)

### Don't assume. Check first, then reply.

Look before you say. Read the file, run the command, query the data, and
only then answer.

-   **Facts:** never state something about the code, the database, the
    vector index, or how a feature behaves unless you have checked it in
    this session. If you haven't checked, say "I haven't checked this"
    instead of presenting a guess as fact.
-   **Worries:** never raise a risk, a problem, or a decision unless you
    have confirmed it is real. First check whether it already exists, is
    already handled, or is actually likely to happen. If it isn't a real
    issue, leave it out.
-   **When unsure:** say what you know, what you don't, and check the
    rest before continuing.

### Don't hallucinate

-   Do not invent file names, function names, library APIs, endpoints,
    table names, Qdrant collection or payload field names, environment
    variables, or config keys. Open the file or read the library's
    docs/installed source to confirm they exist.
-   Do not invent requirements. If this file, `docs/`, or a domain pack
    doesn't specify something, it is **undecided**, not "probably X".
    See Section 7 for the known undecided items.
-   If you are not sure a package or API version behaves a certain way
    (Qdrant client, Gemini SDK, FastAPI, Pydantic), check the installed
    version in this repo before using it.
-   Do not invent domain facts. Never write medical, financial, or legal
    content into prompts, glossaries, gold questions, or test fixtures
    from your own knowledge. Domain content comes from us or from the
    ingested source documents.

### Ask us before every decision

We want to stay in control of the design. **Stop and ask before:**

-   choosing between two reasonable approaches (libraries, patterns,
    structure, chunking strategy, retrieval settings)
-   adding a new dependency or tool
-   changing a database schema, an API endpoint shape, or a
    request/response format
-   changing the shared schemas in `backend/app/schemas/` (`Document`,
    `Chunk`, `RetrievedChunk`, `Citation`, `Answer`, `DomainConfig`):
    every module depends on them
-   changing anything listed in the Tech Stack (Section 3)
-   changing the `domain.yaml` schema (adding, renaming, or removing a
    key)
-   changing the embedding model or the Qdrant collection design: both
    force a full re-index
-   changing eval thresholds, gold questions, or the LLM judge prompt
-   deleting or renaming files, or restructuring folders
-   touching files that belong to another module (Section 5)
-   anything that costs money, calls an external paid API in a new way
    (including bulk embedding or eval runs over a whole domain), or
    handles secrets

When you ask, give **2 to 3 options**, a one-line trade-off for each,
and your recommendation. Wait for our answer before proceeding. Don't
ask about things the code or this file already settles.

### Stay in scope

-   Do only what the current task asks. No drive-by refactors, no "while
    I was here" changes, no extra features.
-   Build the **current module only**. Do not start deferred features
    (Section 2).
-   Prefer the smallest change that works. Small, reviewable changes are
    better than large rewrites.

### Explain in plain English

Some of us are still learning the architecture and need to understand it
well enough to direct the next prompt. After each task, tell us:

1.  what you changed, and **which files**
2.  **why** you did it that way (a short plain-English reason, an
    analogy if it helps)
3.  how to run or test it
4.  anything you did **not** do or couldn't verify

### Verify your work

Run the code, tests, or the endpoint before saying it works. If you
couldn't run it, say so plainly. Never claim something is tested when it
isn't.

-   For any change to chunking, embeddings, retrieval, or generation
    (Modules 3 to 6), run the Module 9 eval for the affected domain and
    report the numbers **before and after**. "It seems better" is not
    evidence.
-   Never edit gold questions, thresholds, or the judge prompt to make
    an eval pass. If the eval fails, report it and stop.

### Never do these

-   **Never run any git command that changes the repo or its history.**
    Version control is done manually by us. That means no `git add`,
    `git commit`, `git push`, `git pull`, `git merge`, `git rebase`,
    `git stash`, `git reset`, `git checkout` / `git switch`, creating or
    deleting branches, tags, or pull requests, even if a task seems to
    need it. Read-only commands (`git status`, `git diff`, `git log`)
    are fine for checking your work.
-   Instead, when a task is done, list every file you created, changed,
    or deleted, so we can review and commit them ourselves.
-   Never put API keys or secrets in any file except `.env`. Only
    `.env.example` with placeholder values is meant to be shared.
-   Never edit `.gitignore` without asking. It must keep `.env`,
    `storage/`, database dumps, and Qdrant snapshots out of the repo
    (source documents may carry licence limits).
-   Never edit the database schema by hand. Schema changes go through
    Alembic migrations.
-   Never delete or recreate a Qdrant collection, or run a full
    re-index, unless we explicitly ask.
-   Never put a domain name in pipeline code (Section 4, rule 1).
-   Never filter results for access control after retrieval (Section 4,
    rule 2).

------------------------------------------------------------------------

## 2. What the Project Is

**A multi-domain research assistant.** It answers questions across
several subject areas (domains such as healthcare, finance, and law)
using **RAG (retrieval-augmented generation)**: it first finds the
relevant passages in a curated document collection, then writes an
answer grounded only in those passages, with citations.

**Problem:** Research questions in specialised fields need answers that
can be traced to trustworthy sources. A plain chatbot answers from
memory, can't show where a claim came from, and may make things up.
Each field also has its own terminology, document formats, and rules
about who may see what.

**Solution:** One shared pipeline, configured per domain. Each domain is
a **domain pack** (a folder of config) that sets its sources,
terminology, chunking, retrieval settings, access rules, answer
behaviour, and evaluation criteria. Adding a domain means adding a
folder, not rewriting code. Think of a game console (the pipeline) and
cartridges (the domains).

**Pipeline (current build scope):** Load domain packs → ingest source
documents → clean and chunk text → embed and index in Qdrant → route the
question to a domain → retrieve passages the user is allowed to see →
generate a cited answer → verify the citations → log the query and
feedback → evaluate each domain against its gold questions.

**Phase 1 scope:** Modules 0 to 11 (Section 6), with **two pilot
domains**. A third domain is added at the end with config only, to
prove the design.

**Deferred (future scope, do not build):** multi-turn memory where
follow-up questions rely on earlier turns, agentic web browsing,
fine-tuned or self-hosted models, multilingual support, and document
upload by end users.

**What the assistant is not:** it gives research summaries with
citations. It does not give personal medical, legal, or financial
advice. Each domain's `prompt.md` sets its disclaimer and refusal rules.

