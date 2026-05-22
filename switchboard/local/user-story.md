# Switchboard User Story

created_at: `2026-05-22T10:35:42+05:30`
updated_at: `2026-05-22T10:51:04+05:30`
last_clarified_at: `2026-05-22T10:22:28+05:30`
last_validated_at: `2026-05-22T10:51:04+05:30`

## Raw Asks

```text
so mainly between me and the agents ops agent which im thinking will be an agent even in the server a node managed project where i will have conversations and do coding from.

and the agent will create this doc and maintain it within the sub project like how if i ask aichat agent to do something it has to evolve the user story in a way after asking me for more explanation you get it ?
```

## Clarifying Questions Asked

- Should user-story docs be global in Agent Ops or local to each managed project/subproject?

## Answers Received

- Project/subproject local is the intended shape.
- Agent Ops can coordinate and also be a node-managed project.
- The active project agent should ask for more explanation and evolve that project's user story.

## Current Interpretation

Switchboard keeps project-local user-story evidence for raw asks, clarifying questions, answers, current interpretation, open ambiguities, and linked task entries. It is evidence for data handoff, not a command surface.

## Open Ambiguities

- Final scoring formula for reverse prompt score.
- Whether user-story records later get a generated JSON projection.
- Whether old `input-prompts` evidence should be archived after manager review.

## Linked Task Entries

- `2026-05-22T10:35:42+05:30 | Accept Loop 11 corrected plan and assign Brick 8A`
