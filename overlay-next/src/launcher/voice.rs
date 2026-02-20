use eframe::egui::{self, Color32, RichText, Ui};

use crate::app::OverlayState;

const GROUP_BG: Color32 = Color32::from_rgb(34, 34, 34);
const GROUP_BORDER: Color32 = Color32::from_rgb(51, 51, 51);

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    let mut config_changed = false;

    ui.add_space(8.0);
    ui.label(
        RichText::new("AUTO VOICE MACRO CONFIG")
            .size(20.0)
            .strong()
            .color(crate::launcher::theme::COLOR_TEXT),
    );
    ui.label(
        RichText::new(
            "Automatically presses 'V' + Number when events occur.\nKeep 'OFF' to disable specific triggers.",
        )
        .size(12.0)
        .color(Color32::from_rgb(140, 140, 140)),
    );

    ui.add_space(10.0);

    let voice_label = if app.config.voice_macros_active {
        "VOICE MACROS: ON"
    } else {
        "VOICE MACROS: OFF"
    };
    if draw_tinted_button(
        ui,
        voice_label,
        [220.0, 40.0],
        if app.config.voice_macros_active {
            Color32::from_rgb(0, 68, 0)
        } else {
            Color32::from_rgb(68, 0, 0)
        },
        if app.config.voice_macros_active {
            Color32::from_rgb(0, 85, 0)
        } else {
            Color32::from_rgb(85, 0, 0)
        },
        if app.config.voice_macros_active {
            Color32::from_rgb(0, 255, 0)
        } else {
            Color32::from_rgb(255, 68, 68)
        },
        Color32::WHITE,
    ) {
        app.config.voice_macros_active = !app.config.voice_macros_active;
        app.launcher.voice_macros_enabled = app.config.voice_macros_active;
        config_changed = true;
    }

    ui.add_space(14.0);

    if cfg!(target_os = "linux")
        && draw_tinted_button(
            ui,
            "REQUEST LINUX PERMISSIONS",
            [320.0, 45.0],
            Color32::from_rgb(51, 51, 51),
            Color32::from_rgb(68, 68, 68),
            Color32::from_rgb(68, 68, 68),
            Color32::from_rgb(170, 170, 170),
        )
    {
        app.launcher.voice_status = match app.request_linux_voice_permissions() {
            Ok(status) => Some(status),
            Err(err) => Some(format!("Permission request failed: {err}")),
        };
    }

    draw_group(ui, |ui| {
        let triggers = [
            (
                "I was Revived",
                "Use '1' for Thanks",
                "voice_revived",
                &mut app.config.voice_macro_revived,
            ),
            (
                "I Teamkilled someone",
                "Use '8' for Sorry",
                "voice_tk",
                &mut app.config.voice_macro_tk,
            ),
            (
                "Killed Infiltrator",
                "Tactical Callout?",
                "voice_kill_infil",
                &mut app.config.voice_macro_kill_infil,
            ),
            (
                "Killed MAX Unit",
                "Taunt?",
                "voice_kill_max",
                &mut app.config.voice_macro_kill_max,
            ),
            (
                "Killed High KD Player (>2.0)",
                "V6 recommended",
                "voice_kill_high_kd",
                &mut app.config.voice_macro_kill_high_kd,
            ),
            (
                "Headshot Kill",
                "Nice Shot?",
                "voice_kill_hs",
                &mut app.config.voice_macro_kill_hs,
            ),
        ];

        egui::Grid::new("voice_macro_grid")
            .num_columns(3)
            .spacing([18.0, 15.0])
            .show(ui, |ui| {
                for (label, hint, id, value) in triggers {
                    if value.trim().is_empty() {
                        *value = "OFF".to_owned();
                    }

                    ui.label(
                        RichText::new(label)
                            .monospace()
                            .size(13.0)
                            .color(Color32::WHITE),
                    );

                    let mut selected = value.clone();
                    egui::ComboBox::from_id_source(id)
                        .selected_text(&selected)
                        .width(80.0)
                        .show_ui(ui, |ui| {
                            ui.selectable_value(&mut selected, "OFF".to_owned(), "OFF");
                            for digit in 0..=9 {
                                let txt = digit.to_string();
                                ui.selectable_value(&mut selected, txt.clone(), txt);
                            }
                        });
                    if &selected != value {
                        *value = selected;
                        config_changed = true;
                    }

                    ui.label(
                        RichText::new(hint)
                            .size(11.0)
                            .color(Color32::from_rgb(85, 85, 85)),
                    );
                    ui.end_row();
                }
            });
    });

    ui.horizontal(|ui| {
        if draw_tinted_button(
            ui,
            "SAVE VOICE MACROS",
            [250.0, 36.0],
            Color32::from_rgb(0, 120, 0),
            Color32::from_rgb(0, 150, 0),
            Color32::from_rgb(0, 255, 0),
            Color32::WHITE,
        ) {
            app.launcher.voice_status = match app.save_settings_now() {
                Ok(()) => Some("Voice macro settings saved.".to_owned()),
                Err(err) => Some(format!("Save failed: {err}")),
            };
        }
    });

    if let Some(status) = &app.launcher.voice_status {
        ui.add_space(8.0);
        ui.label(status);
    }

    if config_changed {
        app.request_settings_save();
    }
}

fn draw_group(ui: &mut Ui, add_contents: impl FnOnce(&mut Ui)) {
    egui::Frame::none()
        .fill(GROUP_BG)
        .stroke(egui::Stroke::new(1.0, GROUP_BORDER))
        .inner_margin(egui::Margin::same(12.0))
        .show(ui, |ui| add_contents(ui));
    ui.add_space(10.0);
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
