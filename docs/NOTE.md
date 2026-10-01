# Things I refused to fake

Running list, folded into the one-page note at step 11.

- No offline or demo mode for model calls. With a missing key the call fails, the failure is traced, and the checkpoint does not pass.
- Model cost is computed from a published price table. Unknown models show as "unpriced" rather than an estimate.
- No cached or canned extraction. `make ingest` reads the five files with both models every time; the golden set is only ever used to score the result, never to produce it.
- The ambiguous digit on the NorthBox photo is physically blotted in the image. It was not marked ambiguous by a flag in the data; the models have to notice.
