# watchOS Golden Path Scenarios

Critical user journeys on the AmakaFlow Apple Watch app.

> **Implementation Note:** Maestro does not support watchOS simulators. The Maestro
> flows in `flows/ios/watch/` are aspirational documentation only. These scenarios
> are actually tested via **XCUITests** in the `amakaflow-ios-app` repository under
> the `AmakaFlowWatch Watch AppUITests` target. See the XCUITest files for the
> executable test implementations.

## Prerequisites

- watchOS Simulator booted (Apple Watch Series 9)
- Paired with iPhone simulator
- AmakaFlow Watch app installed
- Xcode with XCUITest support (for actual test execution)

---

## Scenario: App Launches on Watch

### Step 1: Launch watch app
- **Tool**: Maestro
- **Flow**: `flows/ios/watch/app-launch.yaml`
- **Expected**: Watch app launches to main screen
- **Screenshot**: watch-ios-launch.png

### Step 2: Verify main UI
- **Tool**: Maestro
- **Flow**: `flows/ios/watch/verify-main.yaml`
- **Expected**: Start workout button visible
- **Screenshot**: watch-ios-main.png

---

## Scenario: Start Workout Session

### Step 1: Tap start workout
- **Tool**: Maestro
- **Flow**: `flows/ios/watch/start-workout.yaml`
- **Expected**: Workout session begins
- **Screenshot**: watch-ios-workout-start.png

### Step 2: Verify workout in progress
- **Tool**: Maestro
- **Flow**: `flows/ios/watch/verify-workout-active.yaml`
- **Expected**: Timer, heart rate, and controls visible
- **Screenshot**: watch-ios-workout-active.png

### Step 3: View current exercise
- **Tool**: Maestro
- **Flow**: `flows/ios/watch/view-exercise.yaml`
- **Expected**: Current exercise details shown
- **Screenshot**: watch-ios-exercise.png

---

## Scenario: Quick Log During Workout

### Step 1: Open quick log
- **Tool**: Maestro
- **Flow**: `flows/ios/watch/open-quick-log.yaml`
- **Expected**: Quick log interface appears
- **Screenshot**: watch-ios-quick-log.png

### Step 2: Log a set
- **Tool**: Maestro
- **Flow**: `flows/ios/watch/log-set.yaml`
- **Expected**: Set logged, confirmation shown
- **Screenshot**: watch-ios-set-logged.png

---

## Scenario: End Workout

### Step 1: End workout session
- **Tool**: Maestro
- **Flow**: `flows/ios/watch/end-workout.yaml`
- **Expected**: Workout ends, summary shown
- **Screenshot**: watch-ios-workout-end.png

### Step 2: Verify summary
- **Tool**: Maestro
- **Flow**: `flows/ios/watch/verify-summary.yaml`
- **Expected**: Duration, calories, heart rate summary
- **Screenshot**: watch-ios-summary.png

---

## Pass Criteria

- Watch app launches successfully
- Workout session can be started and ended
- Quick log functionality works
- Summary displays correct information
- Phone-watch sync works (if paired)
