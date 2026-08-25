# Uniting skills and agents into the Research > Plan > Implement workflow pattern

Tutorial by [Ellianna Abrahams](https://github.com/elliesch).

## Learning objectives

By the end of this episode, you will be able to:

- Understand the differences between an **agent**, a **sub-agent**, and a **command** (or skill), and how these relate to the underlying LLM's context window
- Explain the Research > Plan > Implement (RPI) workflow pattern and the problems it solves
- Run RPI on some real world GitHub issues
- Use RPI to write a first pass at an MCP
- Use the `/usage` tool in Claude to monitor context and cost consumption across a session

---

## Attribution

The `/research_codebase`, `/create_plan`, `/implement_plan`, and `/validate_plan` commands used in this tutorial originate from [HumanLayer](https://github.com/humanlayer/humanlayer), who developed the RPI workflow as part of their public work on context engineering for coding agents. Yesterday, Anthony Arendt, Don Setiawan, and Joe Meyer taught us about the concept of context engineering, which is the practice of deliberately designing and managing the full dynamic information environment an LLM sees at runtime (i.e. the mix of tools, history, memory, agents, and retrieved data) rather than letting the context window accumulate anything that a conversation happens to produce. 

We're installing a repackaged, plugin-installable version of the `humanlayer` command set maintained by [jeffh/claude-plugins](https://github.com/jeffh/claude-plugins). If this workflow is useful to you, I recommend checking out HumanLayer's [documentation](https://docs.humanlayer.com/explanation/workflow-phases) and [media](https://thehumansintheloop.substack.com/p/making-agents-mainstream-for-dev-with-dexter-horthy) on context engineering.

---

## Part 1: Background concepts

We're going to test the Research > Plan > Implement workflow that JP Swinski taught us about earlier on the [`earthaccess`](https://github.com/earthaccess-dev/earthaccess) codebase. Let's start by cloning a local copy of `earthaccess` from GitHub:
```bash
git clone https://github.com/earthaccess-dev/earthaccess.git
```

Now let's change directory into `earthaccess`, where we're going to work from today:
```bash
cd earthaccess
```

### What is an agent?

In this tutorial, **agent** refers to an instance of Claude operating with: 
1. a system prompt defining its task
2. a set of tools it can invoke (reading files, running shell commands, searching the web ...)
3. a context window, or the finite amount of text that the underlying model can pay attention to

claude code's main session operates as one agent. When that main agent needs to do a bounded, well-defined task without cluttering its own context, it is a good idea to spawn a **sub-agent**. A sub-agent is a separate Claude instance, with its own isolated context window, that performs this specific task and returns a summary of its findings to the main agent. 

The main agent never sees the sub-agent's intermediate work and only receives its final report. This is precisely the power of the research phase in RPI. Doing many tasks from the main agent clutters the main context window, which grows fuller with each subsequent task. Instead in the research phase of RPI, we instruct the main agent to spawn several sub-agents to index the codebase in parallel, with each specializing in particular tasks. After their tasks are complete, each agent returns a condensed summary rather than flooding the main conversation, and therefore the main context, with every file it read.

Let's take a closer look at a couple of these specialized research agents:
- [codebase-analyzer](https://github.com/jeffh/claude-plugins/blob/main/humanlayer/agents/codebase-analyzer.md)
- [codebase-locator](https://github.com/jeffh/claude-plugins/blob/main/humanlayer/agents/codebase-locator.md)

Let's open claude code and take a closer look at our context. From the terminal run:
```bash
claude
```

Now that you're in claude code, run the following command:
```claude
/context
```

### What is a command?

A **command** (also called a **skill**) is a stored, reusable prompt, saved as a markdown file, that you invoke by typing `/command-name`. Yesterday, Joe Meyer showed us how to build our first skill, and how to see our skills listed in claude. Today we're going to use the research (`/research_codebase`), plan (`/create_plan`), and implement (`/implement_plan`) skills (or commands) from RPI. When RPI was created, these operators were still called commands, but the more accepted terminology today is skill or agent skill.

Let's import these skills and their associated agents from Claude's plugin marketplace. 

Type the following inside claude:
```claude
/plugin marketplace add jeffh/claude-plugins
```

Followed by: 
```
/plugin install humanlayer@jeffh-claude-plugins
```

We can see the skills and agents that have been installed in our plugin by running `/plugin` from claude. Let's do that now.

Let's take a closer look at one of the skills that makes up the RPI workflow:
[research-codebase](https://github.com/jeffh/claude-plugins/blob/main/humanlayer/commands/research_codebase.md)

---

## Part 2: The Research > Plan > Implement workflow pattern

| Phase | What happens | Saved to |
|---|---|---|
| **Research** | The main agent spawns sub-agents to investigate the current state of the codebase, including relevant files, existing patterns, and prior related work, without proposing changes | `thoughts/shared/research/*.md` |
| **Plan** | The main agent synthesizes the research into a phased implementation plan, with explicit, checkable success criteria assigned to each phase | `thoughts/shared/plans/*.md` |
| **Implement** | The main agent executes the plan for each phase, checking off success criteria and pausing for input when reality diverges from the plan expectations | your working tree |

Two RPI design choices are worth calling out explicitly:

1. **Research agents are documentarians, not critics.** The sub-agents used in the research phase (`codebase-locator`, `codebase-analyzer`,
   `codebase-pattern-finder`, and two agents that search any previous `thoughts/` documents, `thoughts-locator` and `thoughts-analyzer`) are instructed to describe what exists accurately, without editorializing about whether it's a good design. This is important, because a plan should be built on an accurate map of the current, *existing* system, not on a sub-agent's opinions about it. In RPI, evaluation and design judgment are reserved for the planning phase, where a human is in the loop.

2. **The plan is the primary human review checkpoint.** Before the main agent begins creating the plan file, you and the agent spec out a complete, concrete description of what is about to change, in what order, and how success will be verified at the end of any implementation *together*. All of this occurs before a single line of code has been touched. This is deliberately the cheapest point in the workflow to catch any misunderstandings, unstated constraints, or scope decisions that need human input and approval.


### Why do we need subagents?

For contained, well-scoped problems, RPI's structure usually isn't worth the overhead. Lilly Thomas gave us a great tutorial on how to create an agent for these kinds of tasks before lunch. The case for RPI is specifically to facilitate success when working with large, complex, or unfamiliar codebases. Why? 

First, a coding agent's output at any step is a function of its current context window and nothing else. That window is "the only lever you have to affect the quality of your output" (Dex Horthy, HumanLayer, [Advanced Context Engineering for Coding Agents](https://www.humanlayer.dev/blog/advanced-context-engineering)). Unstructured prompting tends to lose control of that lever as a task grows, filling the context window with information that isn't necessarily relevant and which competes equally with any information in the context window that ***is*** relevant. 

This means that an LLM's output quality is constrained by both the relevance and volume of text in its context window. If the window is cluttered, for example with a long history, exploratory back-and-forth, and redundant calls, this extraneous information degrades subsequent reasoning even if you haven't reached your token limit. RPI addresses this by splitting the work into three (or more, see [QRSPI](https://github.com/humanlayer/12-factor-agents)) main phases, launched through predefined `/skills`, and persisting the output of each phase to a file, so the conversation can be reset between phases without losing previous progress.

Second, mistakes cost more the earlier they occur in the RPI pipeline. A bad line of code is a local problem, but a flawed plan propagates through every phase built on it, and mistaken context at the research stage can cascade into an entire plan and the code built on it. RPI is built to rely on human review at the early research and plan phases, where a small correction has more leverage than it would later in the workflow, before it compounds into a much larger amount of code. Running a prompt directly from the main agent without a workflow pattern like RPI abstracts away any research or planning that the agent does implicitly, not making room for human feedback even though research and planning is occurring. (Dex Horthy, HumanLayer, [Advanced Context Engineering for Coding Agents](https://www.humanlayer.dev/blog/advanced-context-engineering))

### Why do we need to save persistent artifacts like research and plan files instead of chatting?

RPI's file writing throughout each workflow phase is the structural version of a practice HumanLayer calls "intentional compaction." Rather than letting a conversation run until the context is exhausted, sub-agents are instructed to write out the goal, approach, and current status to a file before resetting, so the next session picks up that progress. RPI does this proactively by creating research and plan documents that are compacted findings and are written *before* context fills up. This allows for resetting between phases (as you'll do with `/reset` later in this tutorial) without losing any previous progress. HumanLayer's own guidance is to keep context utilization around 40–60% throughout a task, treating "getting close to full" as the signal to compact and reset.

---

## Part 3: Setting up the workflow

### Step 1: Create a persistent thoughts directory

If you're still in claude code in the terminal, exit claude by typing `exit` and hitting enter.

From the project root, we're going to run a helper tool from `humanlayer` which will help set up a file tree to save research finding, plans, and implementation summaries to file:

```
npx humanlayer thoughts init
```

This creates a `thoughts/` directory containing a `thoughts/shared/` subtree, which is where the research and plan files described above will be
written. (Note: This can be done differently! Check out Chris Holdgraf's workflow for saving these artifacts in the slack.)

For this tutorial, a single local, default profile is all you need. The full set of `humanlayer` tooling matters more once you're running this workflow across a team or across many repositories, where everyone's agents are drawing research and plans from the same accumulated pool rather than starting from scratch on every task.


### Step 2: Check your baseline usage

Now that we have our codebase and our RPI environment and we are located inside the `earthaccess` directory, let's launch claude code again by typing:
```bash
claude
```

Next we'll check our current usage by typing:

```claude
/usage
```

`/usage` reports your current context window consumption and your usage against any rate or cost limits. We'll run it again after each major step so you can watch context consumption accumulate in real time. This is a useful monitor, and our filling context window will be what motivates us to `/reset` between tasks rather than continuing indefinitely in one session.

---

## Part 3: Answering our "first" GitHub issue with RPI

We'll point claude at a real, open issue on `earthaccess`. Issue [#1425](https://github.com/earthaccess-dev/earthaccess/issues/1425) is a documentation-cleanup issue. It asks for some modifications to the repo's [README.md](https://github.com/earthaccess-dev/earthaccess/blob/main/README.md) file, including a CI badge, documentation of the EDL (Earthdata Login) account-creation step, a citation section, and a description of how the package relates to others in the scientific ecosystem. It is a child of the broader documentation-tracking issue [#1423](https://github.com/earthaccess-dev/earthaccess/issues/1423) for the packages PyOpenSci review.

Now that we have an issue picked out and are launching claude from within a local clone of our codebase, let's get our RPI workflow started. In claude type the following to launch the workflow:

```claude
/research_codebase
```

The command will prompt you for the task. It is a good idea to be explicit, since RPI agents and skills are specifically written to stay within limited creative boundaries. In this case, we provide a link to the issue on GitHub and state the parent/child relationship with another issue explicitly. This relationship is not something a research agent can infer from the child issue's text alone, and getting it wrong means research that satisfies the requested issue in isolation while missing context the parent issue would have supplied. Here is the prompt:

```claude
I'd like to answer this GitHub issue: https://github.com/earthaccess-dev/earthaccess/issues/1425.
It's a child of this parent issue: https://github.com/earthaccess-dev/earthaccess/issues/1423
```

Let's observe the transcript as this runs. You will see Claude use `TodoWrite` to lay out a research plan as a checklist, then dispatch multiple sub-agent
tasks concurrently. For instance, one sub-agent locates the README and related documentation files, another analyzes how the current README is structured, and, if relevant, one would check `thoughts/shared/` for anything from a prior session (there won't be anything yet, since this is your first research pass, but the command checks regardless). Each
sub-agent returns a summary and the main agent synthesizes these into a single research document and writes it to `thoughts/shared/research/`, with an explicit reference to both issue numbers.

**Before continuing, let's open the file that was written.** We can confirm it addresses the scope implied by both issues, not just the child issue's literal text.
This is the cheapest point at which to notice an omission. While correcting a research document costs a sentence, correcting a plan built on an incomplete research document costs a revision cycle, and correcting implemented code built on an incomplete plan costs a rewrite.

Let's check our usage again.

```claude
/usage
```

Run `/usage` again and compare against your baseline. The increase reflects the research sub-agents' work being folded back into the main context as
summaries. This is still smaller than if the sub-agents' full exploration had happened inline, but not zero. This is the trade-off the sub-agent architecture is
making: isolated context per sub-agent, at the cost of some summarization overhead when their results are merged back.

Finally we'll now close out this task's context entirely and start a second, more demanding one.

```claude
/reset
```

`/reset` clears the active conversation. It is distinct from `/compact`, which asks Claude to summarize and shrink the existing conversation rather than discard it, and from starting an entirely new terminal session, which would also lose any project-level state Claude Code has cached for this run. Because our research findings from resolving this GitHub issue were written to `thoughts/shared/research/` rather than existing only in chat history, resetting here costs us nothing. All of the RPI findings persist on disk in saved artifacts and can be referenced again in a future session if this issue is revisited.

---

## Part 4: Answering a more challenging issue with RPI


Now we'll try out RPI on a more advanced issue, [#1434](https://github.com/earthaccess-dev/earthaccess/issues/1434), in which a user reports that `earthaccess.search_data()` silently returned an empty result set with no explanation when a query couldn't find a match. The issue notes several possible causes and has attracted an active comment thread. This is harder than the first task for two reasons: the correct fix is uncertain from the issue text alone, and there is now additional context from the discussion that needs to be factored in.

Let's launch RPI:

```claude
/research_codebase
```

Again, it's a good idea to be explicit with your prompt. Here we make sure to include relevant context, like instructions to pay attention to the comment thread that has important recommendations from lead developers on this repo.

```
I'd like to answer this GitHub issue: https://github.com/earthaccess-dev/earthaccess/issues/1434
considering the conversation in the comments as well. This has a couple of
the lead engineers on the comment thread, and it's important to keep their
recommendations in mind.
```

The second sentence here is useful, because it tells Claude how to weight conflicting input if the thread contains any:
maintainer commentary should be treated as closer to a design decision than a new user's suggestion. This is a judgment call a research agent cannot make unassisted, and stating it costs one sentence.

### Interrupting a running task

When I ran a test of today's tutorial, claude's tool calls suggested that it wass about to attempt GitHub authentication. This would have been a necessary behavior if an earlier task in this session touched a private repository and left that expectation active. This issue and its comment thread are public, so authentication is unnecessary and will only stall the task and waste tokens. Rather than waiting for the sub-agent to fail or resolve on its own, we can interrupt it directly by pressing the `esc` button.

```claude
esc
```

Once we've interrupted the workflow, we can add additional instructions.

```claude
Please don't need to authenticate through GitHub. The issue and comments are public.
```

A short correction issued while claude is mid-task is substantially cheaper than letting it exhaust a bad approach and then re-explaining the constraint after the fact. After we add this additional prompt, claude resumes, fetches the issue and its comments without attempting authentication, and incorporates the maintainers' stated positions into the research document it writes to `thoughts/shared/research/`.

### Scoping the plan before implementation begins

A common pattern in maintainer discussions is that a thread converges on a potential solution. For example, a narrower, immediately actionable improvement (in the issue we're looking at, this would be clearer error messaging when a query returns no results) alongside a broader, more speculative enhancement (as an example in this issue, dataset-specific detection of *why* a query returned no results, which requires more investigation into per-dataset metadata). This is exactly the kind of decision that belongs at the plan-review checkpoint, made explicitly by a human maintainer, rather than leaving this decision for claude to infer during the implementation phase.

Since this GitHub issue is more complex than the first one, once claude has returned the plan, it offers several options for moving forward at varying levels of complexity. This gives us another opportunity to guide claude's scoping at the plan phase of RPI.

```claude
Please move forward with the prototype for Tier 1, but I would prefer to skip Tier 2 for now
```

claude moves forward with the implementation and suggests some relevant tests to try out. In this tutorial, we'll monitor claude's outputs and accept all changes offered. Once the issue has been completed, let's check on our context window again.

```claude
/usage
```

This was a more complex issue than we solved before, which required more research, more sub-agents, more iterations, all which contributed to more context in the window. Similarly to above, we'll now close out this task's context entirely before we start on a different task.

```claude
/reset
```


---

## Part 5: Using RPI to write an `earthaccess` MCP

In the previous two examples, we implemented RPI to *modify* existing code in response to known issues. RPI can also be used to build new code or features. In this section, we're going to try designing and building a new `earthaccess` feature from scratch, where the spec becomes our own request rather than a pre-existing GitHub issue.

We're going to ask claude to build an **MCP server** for `earthaccess`. As Joe Hamman and Jason Gilman taught us earlier today, MCP (the Model Context Protocol) is the open protocol that claude code uses to expose tools to a model. MCPs use the same underlying idea behind the sub-agents dispatched by `/research_codebase` and the plugin commands you installed above, generalized into a standard interface that any tool can implement. An MCP server for `earthaccess` would allow an LLM agent to call functions like "search for a dataset" or "download this data" as structured tool calls, rather than relying on generated shell commands. 

This is exactly the kind of task where having a human in the loop for research and planning matters most. RPI becomes a very powerful tool in this case because it allows us as the users to guide the research and planning alongside claude. We start the workflow the same as above:

```claude
/research_codebase
```

Next we run this prompt. Notice how it's not citing any particular GitHub issue, but is instead proposing an entirely new feature. For that reason we provide context that might connect back to new user experiences in previous research on this repo.

```claude
Can you please help me write an MCP for this codebase to allow new users to use earthaccess as an agent for downloading NASA datasets? I want this to be geared towards users who are new to earth access, and to offer guiding questions
```

As claude runs, we can see that the research phase here looks a little different from before. The sub-agents are locating and analyzing `earthaccess`'s own public functions (search, login, downloading) rather than a specific bug report, and are checking `thoughts/shared/` for anything relevant left over from earlier exploration. The output still saves in the same place as before, `thoughts/shared/research/`. For a design task like this one, it becomes important to check that the research correctly identified which existing functions and workflows like quickstarts in the `earthaccess` repo that this MCP server will need to wrap.

Because of the complexity of the task, the `humanlayer` research agent should surface a *phased* proposal with a minimal set of essential tools first, and more advanced capabilities (for example streaming, provider metadata, conversational dataset discovery) deferred to later phases, rather than generating an entire multi-tool server in one uninterrupted pass. When that proposal arrives, you can choose between options before any implementation code exists, allowing you to narrow the scope before any coding happens.

```claude
Please go with 2. Proceed with Phase 1 implementation (essential 3 tools)
```

With those instructions claude proceeds with the implementation and creates an MCP file. When testing this tutorial, claude create ab MCP file in the project root named `earthaccess_mcp.py`. We'll test that in just a minute. First, though we'll look at our `/usage` to see how our context window filled up for this exploratory problem.

```claude
/usage
```

Finally, let's test our new MCP. We'll exit claude:

```claude
exit
```

Then we can run the following from the terminal:

```bash
python -u earthaccess_mcp.py
```

---


## Further reading
- [An Introduction to Workflow Patterns](https://github.com/responsible-genai-hackweek/workflow-patterns/tree/intro): JP Swinski's introductions to workflows in GenAI from earlier today
- [Build a Tool Using Agent](https://github.com/responsible-genai-hackweek/workflow-patterns/tree/main/tool-using-agent): Lilly Thomas's tutorial on agentic workflows from earlier today
- [Advanced Context Engineering for Coding Agents](https://www.humanlayer.dev/blog/advanced-context-engineering):
  Dex Horthy's original write-up on frequent intentional compaction and the RPI workflow
- [HumanLayer](https://github.com/humanlayer/humanlayer): origin of the RPI command set and the context-engineering ideas behind it
- [`humanlayer` on npm](https://www.npmjs.com/package/humanlayer): CLI reference for the `thoughts` tool, including profiles and syncing
