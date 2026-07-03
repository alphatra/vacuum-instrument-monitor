from devices.base import DeviceProfile
from devices.gp350 import GP350_PROFILE
from devices.vgc402 import VGC402_PROFILE

DEVICE_PROFILES: dict[str, DeviceProfile] = {
    GP350_PROFILE.device_type: GP350_PROFILE,
    VGC402_PROFILE.device_type: VGC402_PROFILE,
}


def get_device_profile(device_type: str) -> DeviceProfile:
    try:
        return DEVICE_PROFILES[device_type]
    except KeyError as error:
        raise ValueError(
            f"Unsupported device_type after detection: {device_type}"
        ) from error
