import screen_brightness_control as sbc
from .logger import logger

class BrightnessController:
    def __init__(self):
        try:
            brightness_list = sbc.get_brightness()
            self.current = brightness_list[0] if brightness_list else 50
        except Exception as e:
            logger.warning(f"Could not get initial brightness: {e}")
            self.current = 50
        self.last_applied = int(self.current)
        
    def set_brightness_by_distance(self, d_thumb_index, min_dist=30, max_dist=250):
        vol_perc = (d_thumb_index - min_dist) / (max_dist - min_dist)
        vol_perc = max(0.0, min(1.0, vol_perc))
        target_brightness = int(vol_perc * 100)
        
        # Smooth lerping
        self.current = self.current + (target_brightness - self.current) * 0.2
        brightness = int(self.current)
        
        try:
            sbc.set_brightness(brightness)
        except Exception as e:
            logger.error(f"Failed to set brightness: {e}")
        return brightness
        
    def adjust_brightness(self, delta):
        target_brightness = self.current + delta
        target_brightness = max(0, min(100, target_brightness))
        
        # Smooth lerping
        self.current = self.current + (target_brightness - self.current) * 0.5
        brightness = int(self.current)
        
        if brightness != self.last_applied:
            try:
                sbc.set_brightness(brightness)
                self.last_applied = brightness
            except Exception as e:
                logger.error(f"Failed to set brightness: {e}")
        return brightness
        
    def set_absolute_brightness(self, target_brightness):
        target_brightness = max(0, min(100, target_brightness))
        self.current = self.current + (target_brightness - self.current) * 0.2
        brightness = int(self.current)
        
        if brightness != self.last_applied:
            try:
                sbc.set_brightness(brightness)
                self.last_applied = brightness
            except Exception as e:
                logger.error(f"Failed to set brightness: {e}")
        return brightness
