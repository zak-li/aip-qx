#!/usr/bin/env python3
"""
cli/ui/ascii.py
-----------------
Pixel-Bird ASCII Art Coloré - Version Dégradé SVG avec Socle Noir
Spécifiquement optimisé pour le banner de démarrage de Pxtly CLI.
"""
import base64
import sys
import zlib

# Sprite compressé du grand oiseau cool
BIRD_DATA = {
    "encoded": "eJw7f+zYeTBiYuBHRudh4sgIKP7202dkhKYSonf19HnIRsG5yMrgglv2HUbTch6bkyDKIAjNXiD7apsxHOF3Hpr7gQhoMrJKiF1Y1SCbSZIyNJXIIsgexI/gBmJVjDXiICEDl4KwsUYrXApTGQAT2S/t",
    "width": 13,
    "height": 14
}

GRADIENT_START = (0, 73, 255)   # Bleu (#0049FF)
GRADIENT_END = (123, 243, 252)  # Cyan (#7BF3FC)

def init_terminal():
    """Initialise le terminal pour l'interprétation des codes couleurs ANSI et l'UTF-8."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hStdOut = kernel32.GetStdHandle(-11)
            if hStdOut != -1:
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode)):
                    kernel32.SetConsoleMode(hStdOut, mode.value | 0x0004)
        except Exception:
            pass

def lerp(a, b, t):
    return int(a + (b - a) * t)

def lerp_rgb(c0, c1, t):
    return (lerp(c0[0], c1[0], t), lerp(c0[1], c1[1], t), lerp(c0[2], c1[2], t))

def get_pixel_color(r, g, b, x, y, width, height):
    """Calcule la couleur avec dégradé diagonal du corps."""
    t = (y / max(1, height - 1) + x / max(1, width - 1)) / 2.0
    t = max(0.0, min(1.0, t))
    
    if (r, g, b) == (2, 0, 15):
        return 35, 35, 40 # Contour visible
    elif (r, g, b) == (237, 242, 243):
        return lerp_rgb(GRADIENT_START, GRADIENT_END, t)
    elif (r, g, b) == (180, 190, 195):
        start_dark = (0, 45, 160)
        end_dark = (75, 160, 175)
        return lerp_rgb(start_dark, end_dark, t)
        
    return r, g, b

def write(s):
    sys.stdout.write(s)
    sys.stdout.flush()

def animate():
    """Affiche le magnifique oiseau de démarrage de Pxtly CLI avec son socle noir."""
    init_terminal()
    
    raw = zlib.decompress(base64.b64decode(BIRD_DATA["encoded"]))
    pixels = [raw[i:i+3] for i in range(0, len(raw), 3)]
    
    width = BIRD_DATA["width"]
    height = BIRD_DATA["height"]
    BLOCK = "██"
    
    # 1. Rendu de l'oiseau
    for y in range(height):
        line = ["  "] # Marge gauche pour centrage esthétique dans la console
        for x in range(width):
            r, g, b = pixels[y * width + x]
            if (r, g, b) == (207, 198, 198):
                line.append("  ")
            else:
                r_adj, g_adj, b_adj = get_pixel_color(r, g, b, x, y, width, height)
                line.append(f"\033[38;2;{r_adj};{g_adj};{b_adj}m{BLOCK}\033[0m")
        write("".join(line) + "\n")
        
    # 2. Rendu du socle de support noir de sécurité
    r_ped, g_ped, b_ped = 35, 35, 40
    
    # Niveau 1 (Supérieur)
    l1 = ["  ", "  "] # Double marge pour centrer la barre réduite
    for _ in range(1, width - 1):
        l1.append(f"\033[38;2;{r_ped};{g_ped};{b_ped}m{BLOCK}\033[0m")
    write("".join(l1) + "\n")
    
    # Niveau 2 (Inférieur)
    l2 = ["  "]
    for _ in range(width):
        l2.append(f"\033[38;2;{r_ped};{g_ped};{b_ped}m▄▄\033[0m")
    write("".join(l2) + "\n")

if __name__ == "__main__":
    animate()
