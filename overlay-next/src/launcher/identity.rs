use crate::app::OverlayState;
use eframe::egui::{self, Color32, RichText, Ui};
use std::sync::mpsc;
use std::thread;

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    poll_identity_search(app);

    egui::ScrollArea::vertical()
        .auto_shrink([false, false])
        .show(ui, |ui| {
            ui.spacing_mut().item_spacing.y = 20.0;

            draw_group(ui, "ACTIVE TRACKING IDENTITY", Some("Select the character you are currently playing."), |ui| {
                let mut selected_character_id = app.active_character_id.clone();
                let selected_text = selected_character_id
                    .as_ref()
                    .and_then(|id| app.characters.iter().find(|c| &c.character_id == id))
                    .map(|c| c.name.clone())
                    .unwrap_or_else(|| "Select Character...".to_owned());

                egui::ComboBox::from_id_source("char_select")
                    .selected_text(selected_text)
                    .width(300.0)
                    .show_ui(ui, |ui| {
                        for c in &app.characters {
                            ui.selectable_value(
                                &mut selected_character_id,
                                Some(c.character_id.clone()),
                                &c.name,
                            );
                        }
                    });
                if selected_character_id != app.active_character_id {
                    app.set_active_character_id(selected_character_id);
                }

                let delete_clicked = draw_tinted_button(
                    ui,
                    "DELETE SELECTED",
                    [180.0, 34.0],
                    Color32::from_rgb(68, 0, 0),
                    Color32::from_rgb(85, 0, 0),
                    Color32::from_rgb(255, 68, 68),
                    Color32::from_rgb(102, 0, 0),
                );
                if delete_clicked {
                    app.delete_active_character();
                }
            });

            draw_group(ui, "ADD NEW CHARACTER", None, |ui| {
                ui.horizontal(|ui| {
                    ui.add_sized(
                        [(ui.available_width() - 88.0).max(180.0), 34.0],
                        egui::TextEdit::singleline(&mut app.launcher.identity.new_char_input)
                            .hint_text("Enter exact character name..."),
                    );
                    if draw_tinted_button(
                        ui,
                        "ADD",
                        [80.0, 34.0],
                        Color32::from_rgb(0, 68, 0),
                        Color32::from_rgb(0, 85, 0),
                        Color32::from_rgb(0, 255, 0),
                        Color32::from_rgb(0, 102, 0),
                    ) {
                        let name = app.launcher.identity.new_char_input.trim().to_string();
                        if !name.is_empty() {
                            let sid = if let Some(s) = &app.config.census_service_id {
                                if s.is_empty() {
                                    "example".to_string()
                                } else {
                                    s.clone()
                                }
                            } else {
                                "example".to_string()
                            };

                            let (tx, rx) = mpsc::channel();
                            app.launcher.identity.search_status =
                                Some("Searching Census...".to_string());
                            app.launcher.identity.search_result = Some(rx);
                            let db_path = app.character_db_path.clone();

                            thread::spawn(move || {
                                let res =
                                    crate::census::lookup_character_by_name(&sid, &name, Some(db_path));
                                let _ = tx.send(res);
                            });
                        }
                    }
                });

                if let Some(status) = &app.launcher.identity.search_status {
                    ui.label(RichText::new(status).italics().color(Color32::from_rgb(170, 170, 170)));
                }
            });

            draw_group(ui, "DEBUG OVERLAY", Some("Force overlay to render without the game running."), |ui| {
                let debug_on = app.launcher.identity.debug_overlay;
                let debug_clicked = if debug_on {
                    draw_tinted_button(
                        ui,
                        "DEBUG OVERLAY: ON",
                        [220.0, 35.0],
                        Color32::from_rgb(0, 68, 0),
                        Color32::from_rgb(0, 85, 0),
                        Color32::WHITE,
                        Color32::from_rgb(0, 102, 0),
                    )
                } else {
                    draw_tinted_button(
                        ui,
                        "DEBUG OVERLAY: OFF",
                        [220.0, 35.0],
                        Color32::from_rgb(68, 0, 0),
                        Color32::from_rgb(85, 0, 0),
                        Color32::WHITE,
                        Color32::from_rgb(102, 0, 0),
                    )
                };
                if debug_clicked {
                    app.launcher.identity.debug_overlay = !app.launcher.identity.debug_overlay;
                }

                ui.label(
                    RichText::new("Toggle the experimental sci-fi HUD style.")
                        .small()
                        .color(Color32::from_rgb(170, 170, 170)),
                );
                let scifi_on = app.scifi_enabled;
                let scifi_clicked = if scifi_on {
                    draw_tinted_button(
                        ui,
                        "SCI-FI HUD: ON",
                        [220.0, 35.0],
                        Color32::from_rgb(0, 68, 0),
                        Color32::from_rgb(0, 85, 0),
                        Color32::WHITE,
                        Color32::from_rgb(0, 102, 0),
                    )
                } else {
                    draw_tinted_button(
                        ui,
                        "SCI-FI HUD: OFF",
                        [220.0, 35.0],
                        Color32::from_rgb(68, 0, 0),
                        Color32::from_rgb(85, 0, 0),
                        Color32::WHITE,
                        Color32::from_rgb(102, 0, 0),
                    )
                };
                if scifi_clicked {
                    app.scifi_enabled = !app.scifi_enabled;
                }

                let move_label = if app.launcher.overlay_move_mode {
                    "MOVE MODE: ON"
                } else {
                    "MOVE MODE: OFF"
                };
                if crate::launcher::theme::primary_button(ui, move_label).clicked() {
                    app.toggle_overlay_move_mode();
                }
            });

            egui::Frame::none()
                .fill(Color32::from_rgb(15, 26, 37))
                .stroke(egui::Stroke::new(1.0, Color32::from_rgb(0, 242, 255)))
                .inner_margin(egui::Margin::same(10.0))
                .show(ui, |ui| {
                    ui.scope(|ui| {
                        let visuals = &mut ui.style_mut().visuals;
                        visuals.widgets.inactive.fg_stroke =
                            egui::Stroke::new(1.0, Color32::from_rgb(0, 255, 0));
                        visuals.widgets.hovered.fg_stroke =
                            egui::Stroke::new(1.0, Color32::from_rgb(0, 255, 0));
                        visuals.widgets.active.fg_stroke =
                            egui::Stroke::new(1.0, Color32::from_rgb(0, 255, 0));
                        ui.add(egui::Checkbox::new(
                            &mut app.overlay_visible,
                            RichText::new("SYSTEM OVERLAY MASTER-SWITCH")
                                .strong()
                                .size(16.0),
                        ));
                    });
                });
        });
}

fn draw_group(
    ui: &mut Ui,
    title: &str,
    subtitle: Option<&str>,
    add_contents: impl FnOnce(&mut Ui),
) {
    egui::Frame::none()
        .fill(Color32::from_rgba_premultiplied(34, 34, 34, 153))
        .stroke(egui::Stroke::new(1.0, Color32::from_rgb(68, 68, 68)))
        .inner_margin(egui::Margin::same(10.0))
        .show(ui, |ui| {
            ui.label(
                RichText::new(title)
                    .size(16.0)
                    .strong()
                    .color(Color32::from_rgb(0, 242, 255)),
            );
            if let Some(subtitle) = subtitle {
                ui.label(
                    RichText::new(subtitle)
                        .size(11.0)
                        .color(Color32::from_rgb(170, 170, 170)),
                );
            }
            ui.add_space(10.0);
            add_contents(ui);
        });
}

fn draw_tinted_button(
    ui: &mut Ui,
    label: &str,
    size: [f32; 2],
    bg: Color32,
    hover: Color32,
    text: Color32,
    border: Color32,
) -> bool {
    ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = bg;
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, border);
        visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.0, text);
        visuals.widgets.hovered.bg_fill = hover;
        visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, text);
        visuals.widgets.hovered.fg_stroke = egui::Stroke::new(1.0, Color32::WHITE);
        ui.add_sized(size, egui::Button::new(label)).clicked()
    })
    .inner
}

fn poll_identity_search(app: &mut OverlayState) {
    let mut search_done = false;
    let mut new_entry = None;
    let mut error_msg = None;

    if let Some(rx) = &app.launcher.identity.search_result {
        match rx.try_recv() {
            Ok(res) => {
                search_done = true;
                match res {
                    Ok(entry) => new_entry = Some(entry),
                    Err(e) => error_msg = Some(e),
                }
            }
            Err(mpsc::TryRecvError::Empty) => {}
            Err(mpsc::TryRecvError::Disconnected) => {
                search_done = true;
                error_msg = Some("Search worker lost".to_string());
            }
        }
    }

    if search_done {
        app.launcher.identity.search_result = None;
        if let Some(entry) = new_entry {
            app.add_or_update_character(entry);
            app.launcher.identity.new_char_input.clear();
            app.launcher.identity.search_status = Some("Character added!".to_string());
        }
        if let Some(err) = error_msg {
            app.launcher.identity.search_status = Some(format!("Error: {}", err));
        }
    }
}
