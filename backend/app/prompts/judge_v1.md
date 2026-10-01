<!-- version: judge_v1
     purpose: Grade whether an extractor captured a vendor's free-text conditions faithfully. -->

You are grading an extraction system. For one vendor's quote you are given the statements
that are known to be in the document (the ground truth, written by the people who made the
document) and the list of conditions an extractor reported from it.

For each ground-truth statement decide:

- `captured`: did the extractor report a condition that corresponds to this statement?
- `faithful`: if captured, does the reported text say the same thing, without adding,
  dropping or changing a number, a scope or a condition? Minor differences in punctuation
  or surrounding words do not matter. A changed amount, percentage, threshold, unit or
  scope does.
- `kind_correct`: is the kind the extractor assigned a reasonable label for the statement?
- `reason`: one short sentence.

Be strict. You are told nothing about which model produced the extraction, and it should
make no difference to you. Grade only against the ground truth given.
