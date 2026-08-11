Two memories were extracted from different conversation turns with the same user.
Determine whether they contradict each other.

MEMORY A:
fact: <<fact_a>>
domain: <<domain_a>>
extracted_at: <<created_at_a>>

MEMORY B:
fact: <<fact_b>>
domain: <<domain_b>>
extracted_at: <<created_at_b>>

Rules:
- Memories contradict if they assert incompatible facts about the same subject
  (e.g., "user prefers R" vs. "user prefers Python" — contradiction; ages 30 and 31 are not)
- Memories do NOT contradict if they are complementary, orthogonal, or one is a
  refinement of the other
- When a user preference evolves over time, the newer memory supersedes the older
  (still counts as "contradicts" so the older one can be decayed)

Respond ONLY with:
{"contradicts": true, "explanation": "one sentence"}
or
{"contradicts": false, "explanation": "one sentence"}
