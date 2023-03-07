from gui import MainWindow
import argparse

def main(nodb=False):
    main_window = MainWindow(nodb=nodb)
    main_window.mainloop()
    
def parse_option():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodb", action='store_true', help="For debugging.")
    return parser.parse_args()
    

if __name__ == "__main__":
    opt = parse_option()
    show = opt.__dict__["nodb"]
    
    main(show)