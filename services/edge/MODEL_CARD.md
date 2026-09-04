# Pilot model card

## Implemented pipeline

- Person and pose detection: `yolo11n-pose.pt` with ByteTrack supplies the person box plus face, shoulder, elbow, wrist, and hip keypoints. CPU is the selected M1 runtime because Ultralytics emits a known pose warning for Apple MPS.
- Employee identity: optional ArUco 4x4 badges `101` and `102`; facial recognition is not implemented.
- PPE: `Landmark-gated controlled PPE verifier v4` uses an item-specific controlled profile: blue mask, red gloves, and blue monitor-only hairnet/apron. It measures only inside pose-landmark-derived face, head, left/right hand, and torso regions. It requires a central connected configured-colour shape; the mask policy accommodates the expected lower-face placement of a surgical mask while retaining coverage, component, span, and quality gates. Total colour pixels alone cannot produce a positive result. It is not a general PPE classifier.
- Tray and inventory: ArUco tags `201` and `301`–`305` with zone/line rules.

## Demo limits

- Camera position, light, badge size, prop colours, and operator path must be controlled.
- Frame decisions use a rolling 15-frame window and require 12 consistent visible observations. A missing result must then remain stable for three seconds before one deduplicated alert. Five seconds of stable compliance is required before the same item can alert again.
- `not_visible`, `checking`, `detected`, and `missing` are distinct. Hidden or low-light anatomy never becomes `missing`. If pose inference is unavailable, person tracking continues and PPE is explicitly unavailable.
- Tomorrow's required rules are mask, left glove, and right glove. Hairnet and apron are visible monitor-only measurements until their demo props and rules are enabled.
- Confidence is a model signal, not a probability of legal or food-safety compliance.
- A supervisor must review detections. This pilot is not regulatory certification.
- A deterministic verifier self-test runs whenever the edge service starts. If the bare-face, peripheral-blue rejection, or central-positive check fails, PPE assessment is disabled and the interface reports it unavailable rather than creating findings.

## Known-failure regression

The earlier detector could classify an unmasked face as masked when a blue chair or background area overlapped the face rectangle. Verifier v2 rejects that archived frame by checking central connected-component size, shape, span, and offset. The automated test suite keeps a synthetic peripheral-blue case and the startup gate exercises the same decision boundary. A live physical 30/30 scenario acceptance is still required on the presentation camera before client use.

## Commercial licensing gate

The optional Ultralytics package and YOLO weights are AGPL-3.0 by default. A proprietary client deployment must either meet AGPL obligations or obtain the relevant commercial licence. The HOG fallback avoids this dependency but has lower detection quality. Complete a legal/model licence review before commercial delivery.

## PPE production gate

The controlled-colour PPE prototype is suitable only for the scripted demonstration. Before a site pilot:

1. Capture consented footage from the actual fixed camera position.
2. Include every required PPE item, missing-item negatives, occlusion, motion blur, and staff/body-size variation.
3. Separate people/locations between train, validation, and test sets.
4. Label mask, gloves, hairnet, and apron boxes; perform a second-person label audit.
5. Fine-tune a commercially approved detector and replace the `LandmarkColourPPEDetector` adapter.
6. Set per-class thresholds from the held-out site test set and document false-positive/false-negative rates.
7. Re-run the 30-scenario acceptance suite and obtain client sign-off.
