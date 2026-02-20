use crate::app::OverlayState;
use eframe::egui::{self, Color32, RichText, Slider, Ui};

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    let mut config_changed = false;
    let mut move_toggle_clicked = false;
    let mut test_clicked = false;
    let mut open_editor_clicked = false;

    let crosshair = &mut app.config.layout.crosshair;

    ui.vertical_centered(|ui| {
        ui.add_space(8.0);

        let checkbox_text = RichText::new("Show Crosshair")
            .size(20.0)
            .strong()
            .color(crate::launcher::theme::COLOR_TEXT);
        if ui.checkbox(&mut crosshair.active, checkbox_text).changed() {
            config_changed = true;
        }

        ui.add_space(10.0);

        ui.label("Crosshair Image (PNG):");
        ui.horizontal(|ui| {
            let mut filename = crosshair.filename.clone().unwrap_or_default();
            if ui
                .add_sized([420.0, 28.0], egui::TextEdit::singleline(&mut filename))
                .changed()
            {
                crosshair.filename = if filename.trim().is_empty() {
                    None
                } else {
                    Some(filename.trim().to_owned())
                };
                config_changed = true;
            }

            if draw_tinted_button(
                ui,
                "...",
                [40.0, 28.0],
                Color32::from_rgb(51, 51, 51),
                Color32::from_rgb(68, 68, 68),
                Color32::from_rgb(85, 85, 85),
                Color32::WHITE,
            ) {
                if crosshair.filename.is_none() {
                    crosshair.filename = Some("crosshair.png".to_owned());
                    app.launcher.crosshair_status = Some("Selected default crosshair image.".to_owned());
                    config_changed = true;
                }
            }
        });

        ui.add_space(8.0);
        ui.label("Crosshair Display Size:");
        ui.horizontal(|ui| {
            if ui
                .add_sized([420.0, 20.0], Slider::new(&mut crosshair.size, 8.0..=256.0))
                .changed()
            {
                config_changed = true;
            }
            ui.label(format!("{} px", crosshair.size.round() as i32));
        });

        ui.add_space(12.0);
        ui.horizontal(|ui| {
            let move_label = if app.launcher.overlay_move_mode {
                "STOP MOVE UI"
            } else {
                "MOVE UI"
            };
            if crate::launcher::theme::primary_button(ui, move_label).clicked() {
                move_toggle_clicked = true;
            }
            if crate::launcher::theme::small_button(ui, "TEST UI").clicked() {
                test_clicked = true;
            }
        });

        ui.add_space(8.0);
        if crate::launcher::theme::small_button(ui, "AUTO-CENTER (Middle)").clicked() {
            crosshair.x = None;
            crosshair.y = None;
            app.launcher.crosshair_status = Some("Crosshair reset to screen center.".to_owned());
            config_changed = true;
        }

        ui.add_space(8.0);
        let shadow_label = if crosshair.shadow {
            "CROSSHAIR SHADOW: ON"
        } else {
            "CROSSHAIR SHADOW: OFF"
        };
        if draw_tinted_button(
            ui,
            shadow_label,
            [240.0, 32.0],
            if crosshair.shadow {
                Color32::from_rgb(0, 68, 0)
            } else {
                Color32::from_rgb(68, 0, 0)
            },
            if crosshair.shadow {
                Color32::from_rgb(0, 85, 0)
            } else {
                Color32::from_rgb(85, 0, 0)
            },
            if crosshair.shadow {
                Color32::from_rgb(0, 255, 0)
            } else {
                Color32::from_rgb(255, 68, 68)
            },
            Color32::WHITE,
        ) {
            crosshair.shadow = !crosshair.shadow;
            app.launcher.crosshair_shadow_enabled = crosshair.shadow;
            config_changed = true;
        }

        ui.add_space(10.0);
        if draw_tinted_button(
            ui,
            "CROSSHAIR EDITOR",
            [260.0, 40.0],
            Color32::from_rgb(0, 64, 128),
            Color32::from_rgb(0, 85, 170),
            Color32::from_rgb(0, 85, 170),
            Color32::WHITE,
        ) {
            if crosshair.filename.is_none() {
                crosshair.filename = Some("crosshair.png".to_owned());
                config_changed = true;
            }
            open_editor_clicked = true;
        }

        if let Some(status) = &app.launcher.crosshair_status {
            ui.add_space(8.0);
            ui.label(status);
        }
    });

    if config_changed {
        app.request_settings_save();
    }
    if move_toggle_clicked {
        app.toggle_overlay_move_mode();
    }
    if test_clicked {
        app.trigger_crosshair_test_ui();
    }
    if open_editor_clicked {
        app.launcher.crosshair_status = match app.launch_crosshair_editor() {
            Ok(()) => Some("Opened crosshair editor.".to_owned()),
            Err(err) => Some(format!("Open crosshair editor failed: {err}")),
        };
    }
}

fn draw_tinted_button(
    ui: &mut Ui,
    text: &str,
    size: [f32; 2],
    bg: Color32,
    hover: Color32,
    border: Color32,
    fg: Color32,
) -> bool {
    ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = bg;
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, border);
        visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.0, fg);

        visuals.widgets.hovered.bg_fill = hover;
        visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, border);
        visuals.widgets.hovered.fg_stroke = egui::Stroke::new(1.0, Color32::WHITE);

        visuals.widgets.active.bg_fill = bg;
        visuals.widgets.active.bg_stroke = egui::Stroke::new(1.0, border);

        ui.add_sized(size, egui::Button::new(RichText::new(text).strong()))
            .clicked()
    })
    .inner
}
