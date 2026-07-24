# Review Findings

## P2: Route recognized compound clauses without an alias match

**Location:** `src/eric_motion_studio/gestures/resolver.py:83-87`

Compound commands containing recognized movement clauses are routed to
`structured_full_body` only when an unrelated definition alias also matched.
For example, `raise the left arm then extend the right arm outward` has valid
configured stage patterns but resolves as unsupported because `matches` is
empty.

Allow recognized multi-clause sequences to route to `structured_full_body`
without requiring an alias match first.

## P2: Honor the requested presentation sweep direction

**Location:** `src/eric_motion_studio/gestures/generators.py:373-375`

The `welcome_presentation` definition accepts and extracts `direction`, but its
stage-sequence generator does not use the slot. Commands requesting
right-to-left and left-to-right sweeps therefore compile to identical
left-to-right poses.

Mirror or reorder the presentation sequence when `Direction.LEFT` is requested.

## P2: Oscillate both arms for two-handed waves

**Location:** `src/eric_motion_studio/gestures/generators.py:191-201`

For `wave with both hands`, slot extraction produces `Side.BOTH` and the initial
pose raises both arms, but the wave-cycle branch updates only the right shoulder
yaw. The left arm remains static while compilation and semantic validation
report success.

For `Side.BOTH`, update both shoulder-yaw joints with mirrored oscillation.

## P2: Do not treat a neutral-reset alias as a modifier

**Location:** `src/eric_motion_studio/gestures/slots.py:210-211`

Normal wording such as `please return to neutral` marks `neutral_return` as an
explicitly provided slot. The resolver then selects `neutral_reset`, which
supports no slots, and incorrectly returns `INVALID_SLOT`.

Distinguish the standalone neutral-reset gesture from a return modifier so
contained neutral aliases resolve successfully.
