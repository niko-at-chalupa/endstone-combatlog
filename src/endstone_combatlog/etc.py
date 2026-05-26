def generate_timer_bar(percentage: float) -> str:
    percentage = max(0.0, min(100.0, percentage))
    
    filled_bars = round(percentage / 10)
    empty_bars = 10 - filled_bars
    
    if percentage <= 30:
        color_code = "§a" # Green
    elif percentage <= 70:
        color_code = "§e" # Yellow
    else:
        color_code = "§c" # Red
        
    bar_string = f"{color_code}{'|' * filled_bars}§8{'|' * empty_bars}§r"
    
    return bar_string