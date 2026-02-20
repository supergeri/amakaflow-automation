# AMA-525: Wearable Form Feedback — Spike Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an Apple Watch PoC that detects squat depth deviations in real time and delivers a haptic cue within 2 seconds, while producing a technical report covering platform feasibility, dataset recommendations, haptic vocabulary validation, and partner device ecosystem.

**Architecture:** On-device 1D-CNN (Core ML) classifies windowed IMU data from CMMotionManager; a RepSegmenter isolates individual reps via peak detection; CHHapticEngine fires a rising-pulse depth cue when depth threshold is missed. Garmin and Wear OS feasibility are evaluated in parallel as research tasks, not PoC code.

**Tech Stack:** Swift/SwiftUI (watchOS 10+), Core Motion, Core ML, Core Haptics, Create ML / coremltools, Python 3.11 (PyTorch + coremltools for model training), Connect IQ SDK (Garmin feasibility), Android/Wear OS (LiteRT feasibility)

**Repo:** `amakaflow-ios-app/amakaflow-ios-app/AmakaFlowCompanion/`
**Xcode project:** `AmakaFlowCompanion.xcodeproj`
**watchOS target dir:** `AmakaFlowWatch Watch App/`
**watchOS test dir:** `AmakaFlowWatch Watch AppTests/`
**Spike scripts:** `../../spike/ama-525/` (relative to Xcode project — i.e. `amakaflow-ios-app/spike/ama-525/`)

---

## Phase 1: Dataset Acquisition & Preparation

### Task 1: Download datasets and set up spike directory

**Files:**
- Create: `spike/ama-525/README.md`
- Create: `spike/ama-525/data/` (directory)
- Create: `spike/ama-525/requirements.txt`

**Step 1: Create spike directory**

```bash
cd /Users/davidandrews/dev/AmakaFlow/amakaflow-ios-app
mkdir -p spike/ama-525/data spike/ama-525/models spike/ama-525/notebooks spike/ama-525/reports
```

**Step 2: Create requirements.txt**

```
torch==2.2.0
coremltools==7.2
numpy==1.26.4
pandas==2.2.0
scipy==1.13.0
scikit-learn==1.4.0
matplotlib==3.8.3
jupyter==1.0.0
requests==2.31.0
tqdm==4.66.2
```

**Step 3: Install dependencies**

```bash
cd spike/ama-525
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: all packages install without error.

**Step 4: Download StrengthSense dataset**

The dataset is available via the arxiv paper supplementary. Check https://arxiv.org/html/2511.02027v1 for the data download link, then:

```bash
# Save to spike/ama-525/data/strengthsense/
# The dataset contains CSVs per participant per activity
```

**Step 5: Download RecGym dataset**

Available at https://archive.ics.uci.edu/dataset/1128 — download and save to `spike/ama-525/data/recgym/`.

**Step 6: Create README**

```markdown
# AMA-525 Spike: Wearable Form Feedback

## Structure
- `data/` - raw datasets (gitignored, too large)
- `models/` - trained Core ML models
- `notebooks/` - Jupyter exploration
- `reports/` - spike findings
- `requirements.txt` - Python deps

## Setup
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

## Datasets
- StrengthSense (2025): arxiv.org/abs/2511.02027
- RecGym (2025): archive.ics.uci.edu/dataset/1128
```

**Step 7: Add data dirs to .gitignore**

Add to `spike/ama-525/.gitignore`:
```
.venv/
data/
__pycache__/
*.pyc
```

**Step 8: Commit**

```bash
git -C /Users/davidandrews/dev/AmakaFlow/amakaflow-ios-app add spike/
git -C /Users/davidandrews/dev/AmakaFlow/amakaflow-ios-app commit -m "chore(AMA-525): spike directory scaffold and dataset setup"
```

---

### Task 2: Extract and normalise wrist-placement IMU data

**Files:**
- Create: `spike/ama-525/notebooks/01_data_exploration.ipynb`
- Create: `spike/ama-525/data_prep.py`

**Context:** StrengthSense has sensors at 10 body locations. We need to extract left/right forearm (LF/RF) channels — the closest simulation of Apple Watch placement. RecGym's sensor placement will need inspection to determine the wrist-equivalent channel.

**Step 1: Write failing test for data loader**

Create `spike/ama-525/test_data_prep.py`:

```python
import pytest
import numpy as np
from data_prep import load_strengthsense_wrist, load_recgym_squat

def test_load_strengthsense_wrist_returns_correct_shape():
    """Wrist data should be (n_samples, 6) — accel xyz + gyro xyz"""
    samples, labels = load_strengthsense_wrist("data/strengthsense/")
    assert samples.ndim == 2
    assert samples.shape[1] == 6
    assert len(labels) == len(samples)

def test_load_recgym_squat_returns_squat_only():
    samples, labels = load_recgym_squat("data/recgym/")
    unique_labels = set(labels)
    assert unique_labels == {"squat"}

def test_samples_are_normalised():
    samples, _ = load_strengthsense_wrist("data/strengthsense/")
    assert np.abs(samples).max() <= 1.0 + 1e-6
```

**Step 2: Run test to verify it fails**

```bash
cd spike/ama-525 && source .venv/bin/activate
pytest test_data_prep.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'data_prep'`

**Step 3: Implement data_prep.py**

Create `spike/ama-525/data_prep.py`:

```python
import os
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

WRIST_CHANNELS = ["LF_acc_x", "LF_acc_y", "LF_acc_z",
                   "LF_gyr_x", "LF_gyr_y", "LF_gyr_z"]

def load_strengthsense_wrist(data_dir: str):
    """Load and normalise wrist-placement channels from StrengthSense."""
    frames, labels = [], []
    for fname in os.listdir(data_dir):
        if not fname.endswith(".csv"):
            continue
        df = pd.read_csv(os.path.join(data_dir, fname))
        available = [c for c in WRIST_CHANNELS if c in df.columns]
        if len(available) < 6:
            continue
        frames.append(df[available].values)
        # Label is activity name encoded in filename (e.g. "squat_p01.csv")
        activity = fname.split("_")[0]
        labels.extend([activity] * len(df))
    samples = np.vstack(frames).astype(np.float32)
    scaler = MinMaxScaler(feature_range=(-1, 1))
    samples = scaler.fit_transform(samples)
    return samples, labels

def load_recgym_squat(data_dir: str):
    """Load squat-only samples from RecGym dataset."""
    frames, labels = [], []
    for root, _, files in os.walk(data_dir):
        for fname in files:
            if "Squat" not in fname and "squat" not in fname:
                continue
            if not fname.endswith(".csv"):
                continue
            df = pd.read_csv(os.path.join(root, fname))
            frames.append(df.select_dtypes(include=[np.number]).values[:, :6])
            labels.extend(["squat"] * len(df))
    samples = np.vstack(frames).astype(np.float32)
    scaler = MinMaxScaler(feature_range=(-1, 1))
    samples = scaler.fit_transform(samples)
    return samples, labels
```

**Step 4: Run test to verify it passes**

```bash
pytest test_data_prep.py -v
```
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add spike/ama-525/data_prep.py spike/ama-525/test_data_prep.py
git commit -m "feat(AMA-525): IMU data loader for StrengthSense + RecGym wrist channels"
```

---

### Task 3: Generate synthetic bad-form reps

**Files:**
- Create: `spike/ama-525/synthetic.py`
- Create: `spike/ama-525/test_synthetic.py`

**Context:** Existing datasets have no form quality labels. We take good-form squat reps and algorithmically introduce three deviations: insufficient depth (truncate the descent phase), knee cave (introduce lateral asymmetry in the X axis), and forward lean (amplify forward accel). Each variant is labelled accordingly.

**Step 1: Write failing tests**

Create `spike/ama-525/test_synthetic.py`:

```python
import numpy as np
import pytest
from synthetic import augment_insufficient_depth, augment_knee_cave, generate_bad_form_dataset

def test_depth_augmentation_shortens_descent():
    """Truncated descent should have smaller vertical displacement."""
    good_rep = np.random.randn(100, 6).astype(np.float32)
    bad_rep = augment_insufficient_depth(good_rep, depth_factor=0.6)
    assert bad_rep.shape == good_rep.shape
    # Vertical accel channel (index 1) should differ
    assert not np.allclose(bad_rep[:, 1], good_rep[:, 1])

def test_knee_cave_adds_lateral_asymmetry():
    good_rep = np.random.randn(100, 6).astype(np.float32)
    bad_rep = augment_knee_cave(good_rep, cave_magnitude=0.3)
    assert bad_rep.shape == good_rep.shape
    assert not np.allclose(bad_rep[:, 0], good_rep[:, 0])

def test_dataset_has_balanced_labels():
    dataset = generate_bad_form_dataset(n_good=100, window_size=100)
    labels = [item[1] for item in dataset]
    from collections import Counter
    counts = Counter(labels)
    assert "good" in counts
    assert "insufficient_depth" in counts
    assert "knee_cave" in counts
```

**Step 2: Run test to verify it fails**

```bash
pytest test_synthetic.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement synthetic.py**

Create `spike/ama-525/synthetic.py`:

```python
import numpy as np
from typing import List, Tuple

def augment_insufficient_depth(rep: np.ndarray, depth_factor: float = 0.6) -> np.ndarray:
    """Simulate not reaching squat depth by scaling down descent phase vertical accel."""
    result = rep.copy()
    descent_end = len(rep) // 2
    # Vertical accel = index 1 (Y axis)
    result[:descent_end, 1] *= depth_factor
    return result

def augment_knee_cave(rep: np.ndarray, cave_magnitude: float = 0.3) -> np.ndarray:
    """Simulate knee cave by introducing lateral (X axis) asymmetry mid-rep."""
    result = rep.copy()
    mid = len(rep) // 2
    # Lateral accel = index 0 (X axis)
    result[mid:, 0] += cave_magnitude * np.sin(np.linspace(0, np.pi, len(rep) - mid))
    return result

def augment_forward_lean(rep: np.ndarray, lean_factor: float = 0.4) -> np.ndarray:
    """Simulate forward lean by amplifying forward accel (Z axis) in descent."""
    result = rep.copy()
    descent_end = len(rep) // 2
    result[:descent_end, 2] *= (1.0 + lean_factor)
    return result

def generate_bad_form_dataset(
    n_good: int = 500,
    window_size: int = 200,
    seed: int = 42
) -> List[Tuple[np.ndarray, str]]:
    """Generate balanced dataset of good and bad-form squat windows."""
    rng = np.random.RandomState(seed)
    dataset = []

    for _ in range(n_good):
        # Simulate a good rep as a smooth sinusoidal motion pattern
        t = np.linspace(0, 2 * np.pi, window_size)
        rep = np.column_stack([
            0.1 * rng.randn(window_size),        # X: lateral (minimal)
            np.sin(t) + 0.05 * rng.randn(window_size),  # Y: vertical (main motion)
            0.3 * np.sin(t / 2) + 0.05 * rng.randn(window_size),  # Z: forward
            0.05 * rng.randn(window_size, 3)      # Gyro (minimal)
        ]).astype(np.float32)
        dataset.append((rep, "good"))
        dataset.append((augment_insufficient_depth(rep), "insufficient_depth"))
        dataset.append((augment_knee_cave(rep), "knee_cave"))
        dataset.append((augment_forward_lean(rep), "forward_lean"))

    return dataset
```

**Step 4: Run tests**

```bash
pytest test_synthetic.py -v
```
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add spike/ama-525/synthetic.py spike/ama-525/test_synthetic.py
git commit -m "feat(AMA-525): synthetic bad-form data augmentation (depth, knee cave, forward lean)"
```

---

## Phase 2: Model Training & Core ML Export

### Task 4: Train lightweight 1D-CNN form classifier

**Files:**
- Create: `spike/ama-525/train.py`
- Create: `spike/ama-525/test_train.py`

**Step 1: Write failing test**

Create `spike/ama-525/test_train.py`:

```python
import numpy as np
import pytest
import torch
from train import FormClassifierCNN, train_model, evaluate_model

def test_model_output_shape():
    """Model should output 4-class logits for a batch of windows."""
    model = FormClassifierCNN(n_channels=6, n_classes=4)
    x = torch.randn(8, 6, 200)  # (batch, channels, time)
    out = model(x)
    assert out.shape == (8, 4)

def test_model_size_under_200kb():
    """Trained model must be small enough for watch deployment."""
    model = FormClassifierCNN(n_channels=6, n_classes=4)
    n_params = sum(p.numel() for p in model.parameters())
    # Each float32 param = 4 bytes; 200KB = 204800 bytes → 51200 params max
    assert n_params < 51200, f"Model too large: {n_params} params"

def test_evaluate_returns_accuracy_dict():
    model = FormClassifierCNN(n_channels=6, n_classes=4)
    X = np.random.randn(20, 6, 200).astype(np.float32)
    y = np.random.randint(0, 4, 20)
    metrics = evaluate_model(model, X, y)
    assert "accuracy" in metrics
    assert 0.0 <= metrics["accuracy"] <= 1.0
```

**Step 2: Run tests to verify they fail**

```bash
pytest test_train.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement train.py**

Create `spike/ama-525/train.py`:

```python
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from typing import Dict

CLASSES = ["good", "insufficient_depth", "knee_cave", "forward_lean"]

class FormClassifierCNN(nn.Module):
    """Lightweight 1D-CNN for form classification. Target: <200KB."""
    def __init__(self, n_channels: int = 6, n_classes: int = 4):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(n_channels, 16, kernel_size=7, padding=3),
            nn.ReLU(),
            nn.MaxPool1d(4),
            nn.Conv1d(16, 32, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.MaxPool1d(4),
            nn.Conv1d(32, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.classifier = nn.Linear(16, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, channels, time)
        features = self.conv(x).squeeze(-1)
        return self.classifier(features)


def train_model(X: np.ndarray, y: np.ndarray, epochs: int = 30, lr: float = 1e-3) -> "FormClassifierCNN":
    """Train the CNN on windowed IMU data. X: (n, channels, time), y: int labels."""
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    train_ds = TensorDataset(torch.FloatTensor(X_train), torch.LongTensor(y_train))
    val_ds = TensorDataset(torch.FloatTensor(X_val), torch.LongTensor(y_val))
    train_dl = DataLoader(train_ds, batch_size=32, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=32)

    model = FormClassifierCNN()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss()

    for epoch in range(epochs):
        model.train()
        for xb, yb in train_dl:
            opt.zero_grad()
            loss_fn(model(xb), yb).backward()
            opt.step()

        if (epoch + 1) % 10 == 0:
            metrics = evaluate_model(model, X_val, y_val)
            print(f"Epoch {epoch+1}/{epochs} — val accuracy: {metrics['accuracy']:.3f}")

    return model


def evaluate_model(model: "FormClassifierCNN", X: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    model.eval()
    with torch.no_grad():
        logits = model(torch.FloatTensor(X))
        preds = logits.argmax(dim=1).numpy()
    accuracy = (preds == y).mean()
    return {"accuracy": float(accuracy)}
```

**Step 4: Run tests**

```bash
pytest test_train.py -v
```
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add spike/ama-525/train.py spike/ama-525/test_train.py
git commit -m "feat(AMA-525): lightweight 1D-CNN form classifier (<200KB, 4 classes)"
```

---

### Task 5: Export trained model to Core ML

**Files:**
- Create: `spike/ama-525/export_coreml.py`
- Create: `spike/ama-525/test_export_coreml.py`

**Step 1: Write failing test**

```python
import os
import pytest
from export_coreml import export_to_coreml

def test_export_creates_mlmodel_file(tmp_path):
    output_path = str(tmp_path / "FormClassifier.mlmodel")
    export_to_coreml(output_path=output_path, use_synthetic=True, n_synthetic=100)
    assert os.path.exists(output_path)

def test_exported_model_under_200kb(tmp_path):
    output_path = str(tmp_path / "FormClassifier.mlmodel")
    export_to_coreml(output_path=output_path, use_synthetic=True, n_synthetic=100)
    size_bytes = os.path.getsize(output_path)
    assert size_bytes < 200 * 1024, f"Model too large: {size_bytes / 1024:.1f}KB"
```

**Step 2: Run to verify failure**

```bash
pytest test_export_coreml.py -v
```
Expected: FAIL

**Step 3: Implement export_coreml.py**

```python
import numpy as np
import torch
import coremltools as ct
from synthetic import generate_bad_form_dataset
from train import FormClassifierCNN, train_model, CLASSES
from sklearn.preprocessing import LabelEncoder

def export_to_coreml(
    output_path: str = "models/FormClassifier.mlmodel",
    use_synthetic: bool = True,
    n_synthetic: int = 500,
    window_size: int = 200,
):
    """Train on synthetic data (or real if available) and export to Core ML."""
    le = LabelEncoder().fit(CLASSES)

    if use_synthetic:
        dataset = generate_bad_form_dataset(n_good=n_synthetic, window_size=window_size)
        # Reshape: (batch, channels, time) for CNN
        X = np.stack([item[0].T for item in dataset]).astype(np.float32)
        y = le.transform([item[1] for item in dataset])
    else:
        raise NotImplementedError("Real dataset loading TBD after dataset evaluation")

    model = train_model(X, y)
    model.eval()

    # Trace the model
    example_input = torch.zeros(1, 6, window_size)
    traced = torch.jit.trace(model, example_input)

    # Convert to Core ML
    mlmodel = ct.convert(
        traced,
        inputs=[ct.TensorType(name="imu_window", shape=(1, 6, window_size))],
        outputs=[ct.TensorType(name="class_logits")],
        minimum_deployment_target=ct.target.watchOS10,
        compute_precision=ct.precision.FLOAT16,  # Reduces size ~2x vs float32
    )

    mlmodel.short_description = "AMA-525 Form Classifier — squat form deviation detection"
    mlmodel.save(output_path)
    print(f"Saved to {output_path} ({os.path.getsize(output_path) / 1024:.1f}KB)")


if __name__ == "__main__":
    export_to_coreml()
```

**Step 4: Run export and verify**

```bash
pytest test_export_coreml.py -v
# Also run the full export to get the real model file
python export_coreml.py
```
Expected: `models/FormClassifier.mlmodel` created, size reported < 200KB.

**Step 5: Commit**

```bash
git add spike/ama-525/export_coreml.py spike/ama-525/test_export_coreml.py
git add spike/ama-525/models/FormClassifier.mlmodel
git commit -m "feat(AMA-525): Core ML export pipeline — FLOAT16 quantised, watchOS 10 target"
```

---

## Phase 3: watchOS PoC

### Task 6: Add CoreMotion sensor capture to watchOS target

**Files:**
- Create: `AmakaFlowCompanion/AmakaFlowWatch Watch App/FormFeedback/MotionCapture.swift`
- Create: `AmakaFlowCompanion/AmakaFlowWatch Watch AppTests/MotionCaptureTests.swift`

**Context:** The watchOS app is at `AmakaFlowWatch Watch App/`. We add a new `FormFeedback/` subdirectory for all spike code so it stays isolated from existing workout code. CMMotionManager must be used on watchOS — HealthKit's motion APIs are not sufficient for raw IMU access.

**Step 1: Write failing unit test**

Create `AmakaFlowWatch Watch AppTests/MotionCaptureTests.swift`:

```swift
import XCTest
@testable import AmakaFlowWatch_Watch_App

final class MotionCaptureTests: XCTestCase {

    func test_motionCapture_initialises_with_100Hz() {
        let capture = MotionCapture()
        XCTAssertEqual(capture.sampleRate, 100.0)
    }

    func test_motionCapture_buffer_is_empty_initially() {
        let capture = MotionCapture()
        XCTAssertTrue(capture.buffer.isEmpty)
    }

    func test_motionCapture_appends_sample_to_buffer() {
        let capture = MotionCapture()
        let sample = IMUSample(
            accX: 0.1, accY: -0.9, accZ: 0.05,
            gyrX: 0.01, gyrY: 0.02, gyrZ: 0.0,
            timestamp: 0.0
        )
        capture.appendSample(sample)
        XCTAssertEqual(capture.buffer.count, 1)
    }

    func test_motionCapture_trims_buffer_to_maxSize() {
        let capture = MotionCapture(maxBufferSize: 5)
        for i in 0..<10 {
            capture.appendSample(IMUSample(
                accX: 0, accY: 0, accZ: 0,
                gyrX: 0, gyrY: 0, gyrZ: 0,
                timestamp: Double(i)
            ))
        }
        XCTAssertEqual(capture.buffer.count, 5)
    }
}
```

**Step 2: Run tests to verify they fail**

```bash
xcodebuild test \
  -project /Users/davidandrews/dev/AmakaFlow/amakaflow-ios-app/amakaflow-ios-app/AmakaFlowCompanion/AmakaFlowCompanion.xcodeproj \
  -scheme "AmakaFlowWatch Watch App" \
  -destination 'platform=watchOS Simulator,name=Apple Watch Series 10 (46mm)' \
  -only-testing:"AmakaFlowWatch Watch AppTests/MotionCaptureTests" \
  2>&1 | tail -20
```
Expected: FAIL — `MotionCapture` and `IMUSample` not found.

**Step 3: Implement MotionCapture.swift**

Create `AmakaFlowWatch Watch App/FormFeedback/MotionCapture.swift`:

```swift
import Foundation
import CoreMotion

struct IMUSample {
    let accX, accY, accZ: Float
    let gyrX, gyrY, gyrZ: Float
    let timestamp: TimeInterval
}

@MainActor
final class MotionCapture: ObservableObject {
    let sampleRate: Double
    private let maxBufferSize: Int
    private let motionManager = CMMotionManager()

    @Published private(set) var buffer: [IMUSample] = []
    @Published private(set) var isCapturing = false

    init(sampleRate: Double = 100.0, maxBufferSize: Int = 600) {
        self.sampleRate = sampleRate
        self.maxBufferSize = maxBufferSize
    }

    func appendSample(_ sample: IMUSample) {
        buffer.append(sample)
        if buffer.count > maxBufferSize {
            buffer.removeFirst(buffer.count - maxBufferSize)
        }
    }

    func startCapture() {
        guard motionManager.isDeviceMotionAvailable else { return }
        motionManager.deviceMotionUpdateInterval = 1.0 / sampleRate
        motionManager.startDeviceMotionUpdates(to: .main) { [weak self] motion, error in
            guard let self, let motion, error == nil else { return }
            let sample = IMUSample(
                accX: Float(motion.userAcceleration.x),
                accY: Float(motion.userAcceleration.y),
                accZ: Float(motion.userAcceleration.z),
                gyrX: Float(motion.rotationRate.x),
                gyrY: Float(motion.rotationRate.y),
                gyrZ: Float(motion.rotationRate.z),
                timestamp: motion.timestamp
            )
            self.appendSample(sample)
        }
        isCapturing = true
    }

    func stopCapture() {
        motionManager.stopDeviceMotionUpdates()
        isCapturing = false
    }
}
```

**Step 4: Run tests**

```bash
xcodebuild test \
  -project /Users/davidandrews/dev/AmakaFlow/amakaflow-ios-app/amakaflow-ios-app/AmakaFlowCompanion/AmakaFlowCompanion.xcodeproj \
  -scheme "AmakaFlowWatch Watch App" \
  -destination 'platform=watchOS Simulator,name=Apple Watch Series 10 (46mm)' \
  -only-testing:"AmakaFlowWatch Watch AppTests/MotionCaptureTests" \
  2>&1 | tail -20
```
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git -C /Users/davidandrews/dev/AmakaFlow/amakaflow-ios-app add \
  "amakaflow-ios-app/AmakaFlowCompanion/AmakaFlowWatch Watch App/FormFeedback/" \
  "amakaflow-ios-app/AmakaFlowCompanion/AmakaFlowWatch Watch AppTests/MotionCaptureTests.swift"
git -C /Users/davidandrews/dev/AmakaFlow/amakaflow-ios-app commit -m "feat(AMA-525): IMUSample + MotionCapture — 100Hz CMMotionManager with ring buffer"
```

---

### Task 7: Implement RepSegmenter (peak detection)

**Files:**
- Create: `AmakaFlowWatch Watch App/FormFeedback/RepSegmenter.swift`
- Create: `AmakaFlowWatch Watch AppTests/RepSegmenterTests.swift`

**Context:** A "rep" is one full squat cycle. We detect it by finding peaks in the vertical acceleration (Y axis) signal — each peak corresponds to the top of the squat (standing position). Two consecutive peaks bookend a rep window.

**Step 1: Write failing tests**

```swift
import XCTest
@testable import AmakaFlowWatch_Watch_App

final class RepSegmenterTests: XCTestCase {

    func makeSamples(yValues: [Float]) -> [IMUSample] {
        yValues.enumerated().map { i, y in
            IMUSample(accX: 0, accY: y, accZ: 0, gyrX: 0, gyrY: 0, gyrZ: 0, timestamp: Double(i) * 0.01)
        }
    }

    func test_noReps_whenBufferTooShort() {
        let segmenter = RepSegmenter()
        let samples = makeSamples(yValues: Array(repeating: 0.5, count: 10))
        XCTAssertTrue(segmenter.extractReps(from: samples).isEmpty)
    }

    func test_detectsOneRep_withSingleValley() {
        let segmenter = RepSegmenter()
        // Simulate one squat: up (1.0) → down (-1.0) → up (1.0)
        var yValues = Array(repeating: Float(1.0), count: 20)
        yValues += Array(repeating: Float(-1.0), count: 20)
        yValues += Array(repeating: Float(1.0), count: 20)
        let reps = segmenter.extractReps(from: makeSamples(yValues: yValues))
        XCTAssertEqual(reps.count, 1)
    }

    func test_repWindow_hasCorrectDimensions() {
        let segmenter = RepSegmenter(windowSize: 200)
        var yValues = Array(repeating: Float(1.0), count: 30)
        yValues += Array(repeating: Float(-1.0), count: 30)
        yValues += Array(repeating: Float(1.0), count: 30)
        let reps = segmenter.extractReps(from: makeSamples(yValues: yValues))
        if let rep = reps.first {
            XCTAssertEqual(rep.count, 200) // Always padded/trimmed to windowSize
        }
    }
}
```

**Step 2: Run to verify failure**

```bash
xcodebuild test \
  -project .../AmakaFlowCompanion.xcodeproj \
  -scheme "AmakaFlowWatch Watch App" \
  -destination 'platform=watchOS Simulator,name=Apple Watch Series 10 (46mm)' \
  -only-testing:"AmakaFlowWatch Watch AppTests/RepSegmenterTests" 2>&1 | tail -15
```
Expected: FAIL

**Step 3: Implement RepSegmenter.swift**

```swift
import Foundation
import Accelerate

final class RepSegmenter {
    let windowSize: Int
    private let minRepSamples = 40  // ~0.4s minimum rep at 100Hz
    private let peakThreshold: Float = 0.3

    init(windowSize: Int = 200) {
        self.windowSize = windowSize
    }

    /// Extract rep windows from IMU buffer. Returns array of (channels × windowSize) arrays.
    func extractReps(from samples: [IMUSample]) -> [[IMUSample]] {
        guard samples.count >= minRepSamples * 2 else { return [] }

        let yValues = samples.map { $0.accY }
        let peaks = findPeaks(in: yValues, minDistance: minRepSamples)

        guard peaks.count >= 2 else { return [] }

        var reps: [[IMUSample]] = []
        for i in 0..<(peaks.count - 1) {
            let start = peaks[i]
            let end = peaks[i + 1]
            let segment = Array(samples[start..<end])
            reps.append(resample(segment, to: windowSize))
        }
        return reps
    }

    private func findPeaks(in signal: [Float], minDistance: Int) -> [Int] {
        var peaks: [Int] = []
        var lastPeak = -minDistance

        for i in 1..<(signal.count - 1) {
            if signal[i] > signal[i-1] && signal[i] > signal[i+1]
               && signal[i] > peakThreshold
               && (i - lastPeak) >= minDistance {
                peaks.append(i)
                lastPeak = i
            }
        }
        return peaks
    }

    /// Pad or trim a segment to exactly `size` samples.
    private func resample(_ segment: [IMUSample], to size: Int) -> [IMUSample] {
        if segment.count == size { return segment }
        if segment.count > size { return Array(segment.prefix(size)) }
        let padding = Array(repeating: segment.last!, count: size - segment.count)
        return segment + padding
    }
}
```

**Step 4: Run tests**

```bash
xcodebuild test ... -only-testing:"AmakaFlowWatch Watch AppTests/RepSegmenterTests" 2>&1 | tail -15
```
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add "AmakaFlowWatch Watch App/FormFeedback/RepSegmenter.swift" \
        "AmakaFlowWatch Watch AppTests/RepSegmenterTests.swift"
git commit -m "feat(AMA-525): RepSegmenter — peak detection rep isolation with windowSize normalisation"
```

---

### Task 8: Integrate FormClassifier Core ML model

**Files:**
- Add: `AmakaFlowWatch Watch App/FormFeedback/FormClassifier.mlmodel` (drag into Xcode)
- Create: `AmakaFlowWatch Watch App/FormFeedback/FormInference.swift`
- Create: `AmakaFlowWatch Watch AppTests/FormInferenceTests.swift`

**Context:** Copy `spike/ama-525/models/FormClassifier.mlmodel` into the watchOS target. Xcode auto-generates a Swift class `FormClassifier` from the `.mlmodel`. `FormInference` wraps it, converts `[IMUSample]` windows to the expected `MLMultiArray` input, and returns a `FormResult`.

**Step 1: Copy model into Xcode target**

```bash
cp spike/ama-525/models/FormClassifier.mlmodel \
   "amakaflow-ios-app/AmakaFlowCompanion/AmakaFlowWatch Watch App/FormFeedback/FormClassifier.mlmodel"
```
Then in Xcode: drag the file into the `AmakaFlowWatch Watch App` target, confirm "Add to target: AmakaFlowWatch Watch App".

**Step 2: Write failing tests**

```swift
import XCTest
@testable import AmakaFlowWatch_Watch_App

final class FormInferenceTests: XCTestCase {

    func makeSamples(count: Int = 200) -> [IMUSample] {
        (0..<count).map { i in
            IMUSample(
                accX: Float.random(in: -1...1),
                accY: Float(sin(Double(i) * 0.1)),
                accZ: Float.random(in: -0.3...0.3),
                gyrX: 0, gyrY: 0, gyrZ: 0,
                timestamp: Double(i) * 0.01
            )
        }
    }

    func test_classify_returnsResult_forValidWindow() throws {
        let inference = FormInference()
        let result = try inference.classify(window: makeSamples())
        XCTAssertNotNil(result)
    }

    func test_classify_result_hasValidClass() throws {
        let inference = FormInference()
        let result = try inference.classify(window: makeSamples())!
        let validClasses = ["good", "insufficient_depth", "knee_cave", "forward_lean"]
        XCTAssertTrue(validClasses.contains(result.label), "Unexpected class: \(result.label)")
    }

    func test_classify_confidence_between_0_and_1() throws {
        let inference = FormInference()
        let result = try inference.classify(window: makeSamples())!
        XCTAssertGreaterThanOrEqual(result.confidence, 0.0)
        XCTAssertLessThanOrEqual(result.confidence, 1.0)
    }
}
```

**Step 3: Implement FormInference.swift**

```swift
import Foundation
import CoreML

struct FormResult {
    let label: String
    let confidence: Float
}

final class FormInference {
    private let model: FormClassifier

    init() {
        self.model = try! FormClassifier(configuration: MLModelConfiguration())
    }

    func classify(window: [IMUSample]) throws -> FormResult? {
        guard window.count == 200 else { return nil }

        // Build MLMultiArray: shape [1, 6, 200]
        let input = try MLMultiArray(shape: [1, 6, 200], dataType: .float32)
        for (i, sample) in window.enumerated() {
            input[[0, 0, i] as [NSNumber]] = NSNumber(value: sample.accX)
            input[[0, 1, i] as [NSNumber]] = NSNumber(value: sample.accY)
            input[[0, 2, i] as [NSNumber]] = NSNumber(value: sample.accZ)
            input[[0, 3, i] as [NSNumber]] = NSNumber(value: sample.gyrX)
            input[[0, 4, i] as [NSNumber]] = NSNumber(value: sample.gyrY)
            input[[0, 5, i] as [NSNumber]] = NSNumber(value: sample.gyrZ)
        }

        let output = try model.prediction(imu_window: input)
        let logits = output.class_logits
        let classes = ["good", "insufficient_depth", "knee_cave", "forward_lean"]

        // Softmax
        var scores = (0..<4).map { Float(truncating: logits[$0]) }
        let maxScore = scores.max()!
        scores = scores.map { exp($0 - maxScore) }
        let sumExp = scores.reduce(0, +)
        scores = scores.map { $0 / sumExp }

        let maxIdx = scores.indices.max(by: { scores[$0] < scores[$1] })!
        return FormResult(label: classes[maxIdx], confidence: scores[maxIdx])
    }
}
```

**Step 4: Run tests**

```bash
xcodebuild test \
  -project .../AmakaFlowCompanion.xcodeproj \
  -scheme "AmakaFlowWatch Watch App" \
  -destination 'platform=watchOS Simulator,name=Apple Watch Series 10 (46mm)' \
  -only-testing:"AmakaFlowWatch Watch AppTests/FormInferenceTests" 2>&1 | tail -20
```
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add "AmakaFlowWatch Watch App/FormFeedback/"
git commit -m "feat(AMA-525): FormInference — Core ML classification wrapper with softmax confidence"
```

---

### Task 9: Implement HapticCoach with depth prompt pattern

**Files:**
- Create: `AmakaFlowWatch Watch App/FormFeedback/HapticCoach.swift`
- Create: `AmakaFlowWatch Watch AppTests/HapticCoachTests.swift`

**Step 1: Write failing tests**

```swift
import XCTest
@testable import AmakaFlowWatch_Watch_App

final class HapticCoachTests: XCTestCase {

    func test_shouldCue_returnsTrue_forDepthDeviation() {
        let coach = HapticCoach()
        let result = FormResult(label: "insufficient_depth", confidence: 0.9)
        XCTAssertTrue(coach.shouldCue(for: result))
    }

    func test_shouldCue_returnsFalse_forGoodForm() {
        let coach = HapticCoach()
        let result = FormResult(label: "good", confidence: 0.95)
        XCTAssertFalse(coach.shouldCue(for: result))
    }

    func test_shouldCue_returnsFalse_belowConfidenceThreshold() {
        let coach = HapticCoach()
        let result = FormResult(label: "insufficient_depth", confidence: 0.4)
        XCTAssertFalse(coach.shouldCue(for: result))
    }

    func test_cueType_forDepthDeviation() {
        let coach = HapticCoach()
        let result = FormResult(label: "insufficient_depth", confidence: 0.9)
        XCTAssertEqual(coach.cueType(for: result), .depthPrompt)
    }
}
```

**Step 2: Implement HapticCoach.swift**

```swift
import Foundation
import CoreHaptics
import WatchKit

enum HapticCue: String, CaseIterable {
    case depthPrompt       // Single rising pulse — "go deeper"
    case stop              // Three sharp rapid taps — "rack it"
    case asymmetryWarning  // Double pulse — "check balance"
    case tempoTooFast      // Short staccato buzz — "slow down"
    case goodRep           // Single crisp tap — positive reinforcement
    case fatigueWarning    // Long fade-out pulse — "you're fading"
}

@MainActor
final class HapticCoach {
    private var engine: CHHapticEngine?
    private let confidenceThreshold: Float = 0.7

    init() {
        setupEngine()
    }

    func shouldCue(for result: FormResult) -> Bool {
        result.label != "good" && result.confidence >= confidenceThreshold
    }

    func cueType(for result: FormResult) -> HapticCue {
        switch result.label {
        case "insufficient_depth": return .depthPrompt
        case "knee_cave":          return .asymmetryWarning
        case "forward_lean":       return .tempoTooFast
        default:                   return .goodRep
        }
    }

    func play(_ cue: HapticCue) {
        guard let engine else {
            // Fallback to WKInterfaceDevice for simulators
            WKInterfaceDevice.current().play(.notification)
            return
        }
        do {
            let pattern = try buildPattern(for: cue)
            let player = try engine.makePlayer(with: pattern)
            try engine.start()
            try player.start(atTime: 0)
        } catch {
            WKInterfaceDevice.current().play(.notification)
        }
    }

    // MARK: - Private

    private func setupEngine() {
        guard CHHapticEngine.capabilitiesForHardware().supportsHaptics else { return }
        engine = try? CHHapticEngine()
    }

    private func buildPattern(for cue: HapticCue) throws -> CHHapticPattern {
        switch cue {
        case .depthPrompt:
            // Single rising pulse over 0.3s
            let intensityCurve = CHHapticParameterCurve(
                parameterID: .hapticIntensityControl,
                controlPoints: [
                    .init(relativeTime: 0, value: 0.1),
                    .init(relativeTime: 0.3, value: 1.0)
                ],
                relativeTime: 0
            )
            let event = CHHapticEvent(
                eventType: .hapticContinuous,
                parameters: [CHHapticEventParameter(parameterID: .hapticIntensity, value: 0.5)],
                relativeTime: 0,
                duration: 0.3
            )
            return try CHHapticPattern(events: [event], parameterCurves: [intensityCurve])

        case .stop:
            // Three sharp taps at 0.1s intervals
            let taps = (0..<3).map { i in
                CHHapticEvent(
                    eventType: .hapticTransient,
                    parameters: [
                        CHHapticEventParameter(parameterID: .hapticIntensity, value: 1.0),
                        CHHapticEventParameter(parameterID: .hapticSharpness, value: 1.0)
                    ],
                    relativeTime: Double(i) * 0.12
                )
            }
            return try CHHapticPattern(events: taps, parameterCurves: [])

        case .goodRep:
            let tap = CHHapticEvent(
                eventType: .hapticTransient,
                parameters: [
                    CHHapticEventParameter(parameterID: .hapticIntensity, value: 0.6),
                    CHHapticEventParameter(parameterID: .hapticSharpness, value: 0.8)
                ],
                relativeTime: 0
            )
            return try CHHapticPattern(events: [tap], parameterCurves: [])

        default:
            let event = CHHapticEvent(
                eventType: .hapticContinuous,
                parameters: [CHHapticEventParameter(parameterID: .hapticIntensity, value: 0.7)],
                relativeTime: 0,
                duration: 0.2
            )
            return try CHHapticPattern(events: [event], parameterCurves: [])
        }
    }
}
```

**Step 3: Run tests**

```bash
xcodebuild test ... -only-testing:"AmakaFlowWatch Watch AppTests/HapticCoachTests" 2>&1 | tail -15
```
Expected: PASS (4 tests)

**Step 4: Commit**

```bash
git commit -m "feat(AMA-525): HapticCoach — 6-cue haptic vocabulary with CHHapticEngine rising pulse depth prompt"
```

---

### Task 10: Wire up FormFeedbackEngine and DebugView

**Files:**
- Create: `AmakaFlowWatch Watch App/FormFeedback/FormFeedbackEngine.swift`
- Create: `AmakaFlowWatch Watch App/FormFeedback/FormFeedbackDebugView.swift`

**Context:** `FormFeedbackEngine` is the coordinator — it subscribes to `MotionCapture`'s buffer, calls `RepSegmenter` on every new sample, and when a complete rep window is ready, runs `FormInference` and fires `HapticCoach`. `FormFeedbackDebugView` shows a live waveform and classification result for the spike demo — not production UI.

**Step 1: Implement FormFeedbackEngine.swift**

```swift
import Foundation
import Combine

@MainActor
final class FormFeedbackEngine: ObservableObject {
    @Published private(set) var lastResult: FormResult?
    @Published private(set) var repCount: Int = 0
    @Published private(set) var isRunning = false

    private let motionCapture = MotionCapture()
    private let segmenter = RepSegmenter()
    private let inference = FormInference()
    private let hapticCoach = HapticCoach()
    private var cancellables = Set<AnyCancellable>()
    private var processedRepCount = 0

    func start() {
        motionCapture.startCapture()
        isRunning = true

        motionCapture.$buffer
            .throttle(for: .milliseconds(200), scheduler: RunLoop.main, latest: true)
            .sink { [weak self] buffer in
                self?.process(buffer: buffer)
            }
            .store(in: &cancellables)
    }

    func stop() {
        motionCapture.stopCapture()
        cancellables.removeAll()
        isRunning = false
    }

    private func process(buffer: [IMUSample]) {
        let reps = segmenter.extractReps(from: buffer)
        guard reps.count > processedRepCount else { return }

        // Process the latest new rep
        let newRep = reps[processedRepCount]
        processedRepCount = reps.count
        repCount = processedRepCount

        guard let result = try? inference.classify(window: newRep) else { return }
        lastResult = result

        if hapticCoach.shouldCue(for: result) {
            hapticCoach.play(hapticCoach.cueType(for: result))
        } else if result.label == "good" {
            hapticCoach.play(.goodRep)
        }
    }
}
```

**Step 2: Implement FormFeedbackDebugView.swift**

```swift
import SwiftUI

struct FormFeedbackDebugView: View {
    @StateObject private var engine = FormFeedbackEngine()

    var body: some View {
        VStack(spacing: 8) {
            Text("FORM FEEDBACK")
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(.secondary)

            if let result = engine.lastResult {
                Text(result.label.replacingOccurrences(of: "_", with: " ").uppercased())
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(result.label == "good" ? .green : .orange)

                Text(String(format: "%.0f%% confidence", result.confidence * 100))
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            } else {
                Text("Waiting for rep...")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }

            Text("Reps: \(engine.repCount)")
                .font(.system(size: 12))

            Button(engine.isRunning ? "Stop" : "Start") {
                engine.isRunning ? engine.stop() : engine.start()
            }
            .buttonStyle(.borderedProminent)
            .tint(engine.isRunning ? .red : .green)
        }
        .padding()
    }
}
```

**Step 3: Build and verify no compiler errors**

```bash
xcodebuild build \
  -project /Users/davidandrews/dev/AmakaFlow/amakaflow-ios-app/amakaflow-ios-app/AmakaFlowCompanion/AmakaFlowCompanion.xcodeproj \
  -scheme "AmakaFlowWatch Watch App" \
  -destination 'platform=watchOS Simulator,name=Apple Watch Series 10 (46mm)' \
  2>&1 | grep -E "error:|warning:|BUILD"
```
Expected: `BUILD SUCCEEDED` with no errors.

**Step 4: Smoke test on simulator**

Open Xcode, run `AmakaFlowWatch Watch App` on the watch simulator. Tap "Start" in `FormFeedbackDebugView`. Confirm no crashes. (Motion data will be zeros on simulator — that's expected.)

**Step 5: Commit**

```bash
git add "AmakaFlowWatch Watch App/FormFeedback/"
git commit -m "feat(AMA-525): FormFeedbackEngine + DebugView — end-to-end PoC coordinator wired up"
```

---

## Phase 4: Platform Feasibility Research

### Task 11: Garmin Connect IQ feasibility test

**Files:**
- Create: `spike/ama-525/reports/garmin-feasibility.md`
- Create: (optional) `amakaflow-garmin-app/test-spikes/AccelTest.mc`

**Context:** The Garmin repo is at `amakaflow-garmin-app/`. Write a minimal Connect IQ app that registers a sensor data listener at the highest available rate, logs how many samples/sec it actually receives, and runs a simple peak-detection loop. Report whether it sustains 25Hz without memory or CPU issues on the Garmin simulator.

**Step 1: Check current Garmin app structure**

```bash
ls /Users/davidandrews/dev/AmakaFlow/amakaflow-garmin-app/
```

**Step 2: Write minimal accelerometer test app**

Create `amakaflow-garmin-app/test-spikes/AccelTest.mc`:

```monkey-c
import Toybox.Sensor;
import Toybox.System;
import Toybox.WatchUi;
import Toybox.Application;

class AccelTestApp extends Application.AppBase {
    private var _sampleCount as Number = 0;
    private var _startTime as Number = 0;

    function onStart(state as Dictionary?) as Void {
        _startTime = System.getTimer();
        var options = {
            :period => 1,                    // 1 = fastest (usually 25Hz on most devices)
            :accelerometer => {:enabled => true, :sampleRate => 25},
            :gyroscope => {:enabled => true, :sampleRate => 25}
        };
        Sensor.registerSensorDataListener(method(:onSensorData), options);
    }

    function onSensorData(sensorData as Sensor.SensorData) as Void {
        _sampleCount++;
        // Simulate peak detection workload: compare Y accel against threshold
        if (sensorData.accelerometerData != null) {
            var accel = sensorData.accelerometerData.y;
            if (accel != null && accel > 500) {  // 500 milli-g threshold
                System.println("Peak detected at sample " + _sampleCount);
            }
        }

        // Report actual sample rate every 100 samples
        if (_sampleCount % 100 == 0) {
            var elapsed = System.getTimer() - _startTime;
            var actualHz = (_sampleCount * 1000.0) / elapsed;
            System.println("Actual Hz: " + actualHz.format("%.1f") + " count=" + _sampleCount);
        }
    }

    function onStop(state as Dictionary?) as Void {
        Sensor.unregisterSensorDataListener();
    }
}
```

**Step 3: Run on Garmin simulator and record output**

```bash
# Requires Connect IQ SDK installed and $CONNECTIQ_HOME set
connectiq build amakaflow-garmin-app/test-spikes/
# Launch in Garmin simulator for target device (e.g. Fenix 7)
# Record the "Actual Hz" output — expected ~25Hz
```

**Step 4: Write feasibility report**

Create `spike/ama-525/reports/garmin-feasibility.md` documenting:
- Actual achieved sample rate
- Memory usage (Connect IQ memory limit is typically 128KB–1MB depending on device)
- Whether peak detection loop causes any lag or OOM
- Verdict: yes/no with specific device constraints noted

**Step 5: Commit**

```bash
git add spike/ama-525/reports/garmin-feasibility.md
git commit -m "docs(AMA-525): Garmin Connect IQ feasibility report"
```

---

### Task 12: Wear OS LiteRT feasibility test

**Files:**
- Create: `spike/ama-525/reports/wearios-feasibility.md`

**Context:** LiteRT is Google's rebranded TFLite (2024). We need to benchmark inference latency for our quantised INT8 model on a mid-range Wear OS device (or emulator). This is a research + benchmarking task — no production code.

**Step 1: Convert model to LiteRT format**

```python
# Add to spike/ama-525/export_tflite.py
import ai_edge_torch  # pip install ai-edge-torch
import torch
from train import FormClassifierCNN

model = FormClassifierCNN()
# Load trained weights if available, else use random init for benchmark
model.eval()

example_input = torch.zeros(1, 6, 200)
edge_model = ai_edge_torch.convert(model, (example_input,))
edge_model.export("models/FormClassifier.tflite")
print(f"TFLite model size: {os.path.getsize('models/FormClassifier.tflite') / 1024:.1f}KB")
```

**Step 2: Benchmark on Wear OS emulator**

Follow Google's LiteRT benchmark tool:
```bash
# Push model to emulator
adb -s <wear_os_emulator> push models/FormClassifier.tflite /data/local/tmp/

# Run LiteRT benchmark
adb shell /data/local/tmp/benchmark_model \
  --graph=/data/local/tmp/FormClassifier.tflite \
  --num_runs=50 \
  --warmup_runs=5 \
  2>&1 | grep -E "avg|min|max"
```

Expected output: avg inference < 100ms for INT8 quantised model.

**Step 3: Write feasibility report**

Document in `spike/ama-525/reports/wearios-feasibility.md`:
- Model size after LiteRT INT8 quantisation
- Inference latency (avg, min, max) on emulator
- Comparison to Apple Watch Neural Engine baseline
- Verdict and recommended deployment constraints

**Step 4: Commit**

```bash
git add spike/ama-525/reports/wearios-feasibility.md
git commit -m "docs(AMA-525): Wear OS LiteRT feasibility report with inference benchmarks"
```

---

## Phase 5: Partner Device Ecosystem

### Task 13: GymAware + Output Sports API outreach and documentation

**Files:**
- Create: `spike/ama-525/reports/partner-devices.md`

**Step 1: GymAware API investigation**

Review the GymAware Cloud API at https://gymaware.zendesk.com/hc/en-us/articles/360001396875-API-Integration

Document:
- Authentication model (API Token + Account ID)
- Available endpoints (rep data, bar velocity, bar path if available)
- Data format (newline-separated JSON stream)
- Whether FLEX device data is accessible via the same API or requires separate integration
- Rate limits and latency characteristics

**Step 2: Output Sports API investigation**

Review Output Sports API at https://www.outputsports.com — navigate to API Integrations section.

Document:
- Authentication model
- Available sensor data streams (velocity, force, power, bar path)
- Whether real-time streaming is supported or batch-only
- SDK availability vs. REST API only

**Step 3: Write partner devices report**

Create `spike/ama-525/reports/partner-devices.md` with:
- Side-by-side comparison table (GymAware vs Output Sports vs RepOne)
- Integration complexity assessment (1–5 scale)
- Data quality: does it give us bar path coordinates or just velocity?
- Recommended first integration target with rationale
- Open questions requiring direct vendor contact

**Step 4: Commit**

```bash
git add spike/ama-525/reports/partner-devices.md
git commit -m "docs(AMA-525): partner device ecosystem report — GymAware, Output Sports, RepOne"
```

---

## Phase 6: Haptic Validation & Final Report

### Task 14: Haptic pattern blind recognition test protocol

**Files:**
- Create: `spike/ama-525/reports/haptic-validation.md`

**Step 1: Build haptic test app on physical Apple Watch**

The HapticCoach is already implemented. Create a simple test view in `FormFeedbackDebugView` that lets you tap through each cue in random order without labelling them — give your test participant a card with 6 pattern names and ask them to match.

Add a test mode to `FormFeedbackDebugView`:

```swift
// Add to FormFeedbackDebugView
Button("Test Haptic") {
    let randomCue = HapticCue.allCases.randomElement()!
    hapticCoach.play(randomCue)
    // Log which cue was played (hidden from test participant)
}
```

**Step 2: Run test with ≥5 athletes**

- 5 participants, 3 reps each of all 6 patterns = 90 total trials
- Record: correct/incorrect identification per pattern
- Target: ≥80% per pattern

**Step 3: Document results and iterate on failed patterns**

Any pattern with <80% recognition needs redesign. Common fixes: increase intensity contrast between patterns, add more time between events, change duration.

**Step 4: Write validation report**

Document in `spike/ama-525/reports/haptic-validation.md`:
- Recognition accuracy per pattern (%)
- Patterns that passed/failed threshold
- Revisions made and rationale
- Final approved haptic vocabulary v0.1

**Step 5: Commit**

```bash
git add spike/ama-525/reports/haptic-validation.md
git commit -m "docs(AMA-525): haptic vocabulary v0.1 blind recognition test results"
```

---

### Task 15: Write spike technical findings report

**Files:**
- Create: `spike/ama-525/reports/AMA-525-spike-findings.md`

**Step 1: Compile all findings**

The report covers all four spike questions with evidence from the prior tasks:

```markdown
# AMA-525: Wearable Form Feedback — Spike Findings

## 1. Dataset Recommendation
[StrengthSense vs RecGym comparison, the form-quality gap, synthetic augmentation results, accuracy achieved on validation set]

## 2. Platform Feasibility
| Platform | Verdict | Evidence | Constraints |
|----------|---------|----------|-------------|
| Apple Watch | ✅ Go | [latency measured, battery test result] | watchOS 10+ required |
| Wear OS | ✅/⚠️ | [LiteRT benchmark results] | [device-specific constraints] |
| Garmin | ✅/⚠️ | [Connect IQ feasibility report] | Classical only, ~70% accuracy ceiling |

## 3. Partner Device Ecosystem
[Summary from partner-devices.md, recommended first integration]

## 4. Haptic Language
[Recognition accuracy per pattern, final vocabulary v0.1]

## Recommendation: Path to Full Implementation
[Which approach to pursue per platform, dataset collection plan if needed, Phase 2 scope]
```

**Step 2: Commit report**

```bash
git add spike/ama-525/reports/
git commit -m "docs(AMA-525): spike findings report — datasets, platform feasibility, haptics, partner devices"
```

**Step 3: Copy report to main docs**

```bash
cp spike/ama-525/reports/AMA-525-spike-findings.md \
   /Users/davidandrews/dev/AmakaFlow/amakaflow-automation/AMA-525-spike-findings.md
git -C /Users/davidandrews/dev/AmakaFlow/amakaflow-automation add AMA-525-spike-findings.md
git -C /Users/davidandrews/dev/AmakaFlow/amakaflow-automation commit -m "docs(AMA-525): spike findings report"
```

---

## Definition of Done Checklist

- [ ] Python training pipeline runs end-to-end: datasets → synthetic augmentation → trained model → `FormClassifier.mlmodel`
- [ ] `FormClassifier.mlmodel` < 200KB
- [ ] watchOS app builds and runs on simulator without errors
- [ ] All unit tests pass: `MotionCaptureTests`, `RepSegmenterTests`, `FormInferenceTests`, `HapticCoachTests`
- [ ] End-to-end latency measured on physical Apple Watch: < 2s from rep completion to haptic cue
- [ ] Battery test: ≥45 minutes continuous with CoreMotion active
- [ ] Garmin feasibility report: yes/no verdict with evidence
- [ ] Wear OS feasibility report: yes/no verdict with latency benchmark
- [ ] Partner device report: GymAware + Output Sports API access status confirmed
- [ ] Haptic validation: ≥80% blind recognition per pattern (≥5 athletes)
- [ ] Spike findings report written and committed
