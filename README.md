# pfa-week06
MIDTERM PROJECT
Color Script Template Generator 
This is an interface that connects to Photoshop that allows the user to create a spread of images with color swatches based on the files the user submits. User can adjust the orientation of everything and sends the layout to photoshop as a png as well as creates a color palette file for the user to download and import into photoshop. 

WHERE THE TOOL LIVES: This tool is a standalone interface that connects to Photoshop 

WHAT THE TOOL DOES: Opens an interface that does the following:
-Allows users to input a selection of images and create a spread template
-Allows user to change the orientation/placement and count of swatches
-Contains options to save as an individual png but also sends image directly to photoshop
-Turns color palette swatches into a downloadable file users can import to Photoshop (the tool cannot do that itself)

HOW TO INSTALL AND RUN: 
1. Requirements — Python 3.10+, pygame, pywin32, Photoshop
2. Install — python -m pip install pygame pywin32., and photoshop bridge tool in this repo
3. Run — python palette_gui.py.
4. Using the window — Images panel, collapsible Options (with More options for shape/gap/hex labels/background), interactive preview (drag items, wheel zoom, pan, Reset layout), and the four action buttons.
5. The one manual step — since Photoshop's Swatches panel isn't scriptable, load the auto-written color_script.aco via the panel's ☰ → Load Swatches.

WHAT WORKS NOW:

The UI runs the way I wanted it to and the preview window's functions (moving around the images,text as well as changing the text) worked the way I wanted them to. The image export does not have any issues.  

WHAT DOESN'T WORK YET:

The tool cannot import the palette swatches into Photoshop automatically. It told me it was unable to do that. I'm going to keep testing this to see if I can get it to do this without having to manually download the file. 


PEER RUN: 

