from pathlib import Path


application = Path(defines["app"]).resolve()
files = [str(application)]
symlinks = {"Applications": "/Applications"}
icon = str(application / "Contents" / "Resources" / "app-icon.icns")
background = defines["background"]
format = "UDZO"
filesystem = "HFS+"
window_rect = ((220, 180), (680, 440))
icon_locations = {application.name: (190, 220), "Applications": (490, 220)}
icon_size = 96
text_size = 13
label_pos = "bottom"
arrange_by = None
scroll_position = (0, 0)
grid_spacing = 64
default_view = "icon-view"
show_icon_preview = False
include_icon_view_settings = True
include_list_view_settings = False
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
