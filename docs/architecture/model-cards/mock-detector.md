# Model card — `DeterministicMockDetector`

**This is not a model.** It is a test fixture that produces model-shaped output.
This card exists because a fixture that is not labelled as one eventually gets
quoted as a result.

## Summary

| | |
|---|---|
| **Name** | `surface-defect-detector` |
| **Version** | `0.3.0-demo` |
| **Type** | Deterministic hash function. No weights, no training, no inference |
| **Location** | `packages/detector/mock.py` |
| **Accuracy** | **None claimed, none measurable** |
| **Intended use** | Demonstration and testing of the governance path around a detector |
| **Out of scope** | Any inspection, quality, safety or production decision |

## How it works

The SHA-256 of `frame_hash | station_id | product_sku` seeds two independent
bytes. One selects a label from the seven-class taxonomy; the other sets a
confidence in `[0.40, 0.99]`. A residual class is emitted alongside so
downstream code sees a real distribution.

Fixture hashes can be pinned to a known label and confidence through
`pin_scenario()`, which is how `data/fixtures/demo-scenarios.json` guarantees
the same seven scenarios on every machine.

There is no relationship between the input and the output beyond a hash. **The
same frame always produces the same "defect", and a different frame produces a
different one, for no reason connected to what is in the image.**

## Why it exists

Three properties that a real model cannot provide during a demonstration:

- **Reproducible.** The same input produces the same output on any machine, so the demo does not depend on a conference network and the test suite does not flake.
- **Free.** No endpoint, no GPU, no subscription.
- **Substitutable.** It satisfies the same `Detector` protocol as `OnnxDetector` and `AzureMLEndpointDetector`. Moving to a real model changes one configuration value.

The point of the platform is what happens *around* the detector. This fixture
lets all of that be exercised without a trained model while the settings
validator keeps local mode from selecting a cloud provider or enabling writes.

## Taxonomy

Seven classes, in `packages/contracts/taxonomy.py`. **A demonstration taxonomy
for a synthetic manufacturing line, not derived from any real inspection
dataset.**

| Label | Default severity | Safety relevant |
|---|---|---|
| `no_defect` | none | no |
| `surface_scratch` | cosmetic | no |
| `discoloration` | cosmetic | no |
| `misalignment` | minor | no |
| `seal_gap` | major | **yes** |
| `weld_porosity` | major | **yes** |
| `structural_crack` | critical | **yes** |

Severity here is an **input to the policy engine, never a verdict**. Policy
decides the disposition and is free to disagree with the taxonomy default.

## Limitations

- No images are processed. `frame_uri` is carried through and never opened.
- The decision threshold (`0.62`) is an arbitrary demonstration value, not calibrated against anything.
- Confidence has no calibration meaning. A "0.94 confidence" is a byte divided by 255.
- The class distribution is uniform over the hash space and does not resemble any real defect distribution, which is heavily skewed toward `no_defect`.
- Bounding boxes are a fixed rectangle.

## Ethical and safety considerations

A real defect detector in a manufacturing line participates in decisions with
**safety consequences**. Three classes here are marked safety-relevant, and the
policy engine escalates them to a human.

That escalation is real and tested. **The detection is not.** Any deployment
must:

1. Train on the customer's own labelled inspection data.
2. Establish accuracy, and specifically the false-negative rate on safety-relevant classes, against a held-out set.
3. Calibrate the decision threshold against the cost asymmetry — a missed structural crack and a false alarm are not equally expensive.
4. Monitor drift, and re-baseline the evaluation gate after every model change.
5. Publish a model card that replaces this one.

## Replacing it

```bash
# Locally executed ONNX graph
REAP_DETECTOR_PROVIDER=onnx
REAP_DETECTOR_ONNX_MODEL_PATH=/models/detector.onnx

# Azure ML managed online endpoint
REAP_MODE=azure_dev
REAP_DETECTOR_PROVIDER=aml
REAP_DETECTOR_AML_ENDPOINT_URL=https://<endpoint>.<region>.inference.ml.azure.com/score
```

No other change is required, which is the property the plane exists to provide.

After replacing it, **every evaluation threshold must be re-baselined**. The
current scores describe this fixture.
