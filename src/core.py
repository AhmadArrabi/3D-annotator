import numpy as np
import nibabel as nib

def create_synthetic_phantom(shape=(128, 128, 128)):
    """
    Creates a synthetic 3D volume with a blob and some noise.
    Shape: (X, Y, Z)
    """
    volume = np.zeros(shape, dtype=np.float32)
    
    # Grid
    x = np.linspace(-1, 1, shape[0])
    y = np.linspace(-1, 1, shape[1])
    z = np.linspace(-1, 1, shape[2])
    xx, yy, zz = np.meshgrid(x, y, z, indexing='ij')
    
    # Main blob (body)
    radius = 0.5
    mask_body = (xx**2 + yy**2 + (zz*0.5)**2) < radius**2
    volume[mask_body] = 100.0
    
    # Smaller blob (humeral head - asymmetric feature)
    # Place it off-center: +X (left), +Z (top), 0 Y
    mask_head = ((xx - 0.4)**2 + (yy)**2 + (zz - 0.5)**2) < 0.15**2
    volume[mask_head] = 200.0  # Dense bone
    
    # Noise
    volume += np.random.normal(0, 5, shape)
    
    # Normalize to 0-255 or typical HU range? Let's keep arbitrary for now.
    return volume

def load_ct_scan(path=None):
    """
    Loads a CT scan from a path or generates a synthetic one.
    Returns: numpy array
    """
    if path is None:
        print("No path provided, generating synthetic phantom...")
        return create_synthetic_phantom()
    
    try:
        nii = nib.load(path)
        data = nii.get_fdata()
        # Handle orientation later if needed. Assume canonical for now.
        return data
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return create_synthetic_phantom()

def generate_aip(volume, axis):
    """
    Generates Average Intensity Projection along a given axis.
    axis: axis to project along (collapse).
    """
    return np.mean(volume, axis=axis)

