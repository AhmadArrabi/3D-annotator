# 3D CT Annotator

A Python-based GUI tool for efficiently annotating 3D landmarks on CT scans using bounding boxes. Designed for medical research data collection.

![Annotator Overview](./assets/overview.png)

## Features
- **Multi-View Interface**: AP, Lateral, and MPR (Axial, Coronal, Sagittal) views.
- **Smart Navigation**: Quickly switch between patients and landmarks.
- **Auto-Saving**: Never lose progress; annotations are saved automatically when moving to the next landmark.
- **Modifiable History**: Navigate back to previous landmarks to view or correct your submissions.
- **Z-Axis Locking**: Guides align across views to ensure accurate 3D positioning.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd 3D-annotator
    ```

2.  **Install Dependencies**:
    Ensure you have Python installed. Then run:
    ```bash
    pip install -r requirements.txt
    ```
    *(Requires: `numpy`, `matplotlib`, `nibabel`, `tkinter`)*

## Setup Data

The tool expects NIfTI files (`.nii.gz`) in the `data` directory.

1.  Create a `data` folder in the project root if it doesn't exist.
2.  Place your CT scan files inside:
    ```
    3D-annotator/
    ├── data/
    │   ├── case001_ct.nii.gz
    │   └── case002_ct.nii.gz
    ├── src/
    │   └── annotator.py
    ```

## Step-by-Step Guide

1.  **Launch the Application**:
    ```bash
    python src/annotator.py
    ```

2.  **Login**:
    - Enter your **Resident Name** in the "User Info" box. This is required to save data.

3.  **Annotate**:
    - Select a landmark from the dropdown or use the **Next LM** button.
    - **AP View**: Click and drag to draw a bounding box around the landmark.
    - **Lateral View**: Draw the corresponding box.
    - *Tip: A cyan line will appear to help you align the Z-height between views.*

4.  **Verify**:
    - Click **Visual Check (MPR)** to see the cross-sectional views of your selection.

5.  **Save & Continue**:
    - Click **Next LM** (or **Next Case**) to auto-save your current annotation and move to the next item.
    - If you need to fix a mistake, simply navigate back (`< Prev LM`), redraw the box, and it will update the record.

## Output

Annotations are saved to `annotations.csv` in the project root.

**Format**:
`CaseID, FileName, Resident, LandmarkIdx, LandmarkName, X, Y, Z, AP_Box, Lat_Box`

- **X, Y, Z**: Calculated 3D center of the annotation.
- **AP_Box**: `x_min;x_max;z_min;z_max` (Volume X-axis and Z-axis).
- **Lat_Box**: `y_min;y_max;z_min;z_max` (Volume Y-axis and Z-axis).
     - *Note: Y-axis corresponds to the horizontal axis in the Lateral view.*

---
**Note**: The application uses an "Append-Only" log for safety. If you modify an annotation, a new row is added to the CSV.
