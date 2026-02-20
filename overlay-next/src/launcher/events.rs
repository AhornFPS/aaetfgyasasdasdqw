use std::collections::HashMap;

use eframe::egui::{self, RichText, Slider, Ui};

use crate::app::OverlayState;

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    ensure_event_slots_initialized(app);
    ui.spacing_mut().item_spacing.y = 8.0;
    let desired_editor_h: f32 = 300.0;
    let avail_h: f32 = ui.available_height();
    let editor_h = desired_editor_h.min(avail_h.max(0.0));
    let top_h = (avail_h - editor_h - 6.0).max(0.0);

    ui.allocate_ui_with_layout(
        egui::vec2(ui.available_width(), top_h),
        egui::Layout::top_down(egui::Align::Min),
        |ui| {
            egui::ScrollArea::vertical()
                .auto_shrink([false, false])
                .show(ui, |ui| {
                    draw_preset_bar(app, ui);
                    draw_master_controls(app, ui);
                    ui.add_space(8.0);

                    let grid_h = ui.available_height().max(120.0);
                    ui.allocate_ui_with_layout(
                        egui::vec2(ui.available_width(), grid_h),
                        egui::Layout::top_down(egui::Align::Min),
                        |ui| draw_event_category_grid(app, ui),
                    );
                });
        },
    );

    ui.add_space(6.0);
    ui.allocate_ui_with_layout(
        egui::vec2(ui.available_width(), editor_h),
        egui::Layout::top_down(egui::Align::Min),
        |ui| draw_event_editor(app, ui),
    );
}

fn draw_preset_bar(app: &mut OverlayState, ui: &mut Ui) {
    let previous_slot = app.launcher.events.active_slot;
    ui.horizontal_wrapped(|ui| {
        ui.label(
            RichText::new("PRESET:")
                .strong()
                .size(12.0)
                .color(egui::Color32::from_rgb(0, 242, 255)),
        );
        egui::ComboBox::from_id_source("event_slot_combo")
            .selected_text(
                app.launcher
                    .events
                    .slot_names
                    .get(app.launcher.events.active_slot)
                    .cloned()
                    .unwrap_or_else(|| "default".to_owned()),
            )
            .width(180.0)
            .show_ui(ui, |ui| {
                for (idx, name) in app.launcher.events.slot_names.iter().enumerate() {
                    ui.selectable_value(&mut app.launcher.events.active_slot, idx, name);
                }
            });

        if draw_slot_button(
            ui,
            "+ NEW",
            [86.0, 32.0],
            egui::Color32::from_rgb(0, 51, 0),
            egui::Color32::from_rgb(0, 68, 0),
            egui::Color32::from_rgb(102, 255, 102),
            egui::Color32::from_rgb(0, 102, 0),
        ) {
            save_current_slot_profile(app);
            let new_name = format!("slot_{}", app.launcher.events.slot_names.len() + 1);
            app.launcher
                .events
                .slot_profiles
                .insert(new_name.clone(), app.config.legacy_visual_overrides.clone());
            app.launcher.events.slot_names.push(new_name);
            app.launcher.events.active_slot = app.launcher.events.slot_names.len() - 1;
            app.launcher.events.rename_input.clear();
            app.launcher.events.status = Some("Created slot".to_owned());
            sync_event_slots_into_config(app);
        }
        if draw_slot_button(
            ui,
            "DELETE",
            [86.0, 32.0],
            egui::Color32::from_rgb(51, 0, 0),
            egui::Color32::from_rgb(68, 0, 0),
            egui::Color32::from_rgb(255, 102, 102),
            egui::Color32::from_rgb(102, 0, 0),
        ) {
            if app.launcher.events.slot_names.len() > 1 {
                let removed = app
                    .launcher
                    .events
                    .slot_names
                    .remove(app.launcher.events.active_slot);
                app.launcher.events.slot_profiles.remove(&removed);
                app.launcher.events.active_slot = app.launcher.events.active_slot.saturating_sub(1);
                load_active_slot_profile(app);
                app.request_settings_save();
                app.launcher.events.status = Some("Deleted slot".to_owned());
                sync_event_slots_into_config(app);
            } else {
                app.launcher.events.status = Some("Default slot cannot be deleted".to_owned());
            }
        }
        if draw_slot_button(
            ui,
            "RENAME",
            [90.0, 32.0],
            egui::Color32::from_rgb(34, 34, 34),
            egui::Color32::from_rgb(48, 48, 48),
            egui::Color32::from_rgb(0, 242, 255),
            egui::Color32::from_rgb(68, 68, 68),
        ) {
            let input = app.launcher.events.rename_input.trim().to_owned();
            if !input.is_empty() {
                let old = app.launcher.events.slot_names[app.launcher.events.active_slot].clone();
                if old != input && !app.launcher.events.slot_profiles.contains_key(&input) {
                    if let Some(profile) = app.launcher.events.slot_profiles.remove(&old) {
                        app.launcher
                            .events
                            .slot_profiles
                            .insert(input.clone(), profile);
                    }
                    app.launcher.events.slot_names[app.launcher.events.active_slot] = input;
                    app.request_settings_save();
                    app.launcher.events.status = Some("Renamed slot".to_owned());
                    sync_event_slots_into_config(app);
                } else {
                    app.launcher.events.status =
                    Some("Rename failed (duplicate or same)".to_owned());
                }
            }
        }
        if draw_slot_button(
            ui,
            "IMPORT",
            [86.0, 32.0],
            egui::Color32::from_rgb(34, 34, 34),
            egui::Color32::from_rgb(48, 48, 48),
            egui::Color32::from_rgb(0, 242, 255),
            egui::Color32::from_rgb(68, 68, 68),
        ) {
            let slot = app.launcher.events.slot_names[app.launcher.events.active_slot].clone();
            match app.import_event_slot_from_disk(&slot) {
                Ok(map) => {
                    app.launcher.events.slot_profiles.insert(slot.clone(), map);
                    load_active_slot_profile(app);
                    app.request_settings_save();
                    app.launcher.events.status = Some("Imported slot from disk".to_owned());
                    sync_event_slots_into_config(app);
                }
                Err(err) => app.launcher.events.status = Some(err),
            }
        }
        if draw_slot_button(
            ui,
            "EXPORT",
            [86.0, 32.0],
            egui::Color32::from_rgb(34, 34, 34),
            egui::Color32::from_rgb(48, 48, 48),
            egui::Color32::from_rgb(0, 242, 255),
            egui::Color32::from_rgb(68, 68, 68),
        ) {
            let slot = app.launcher.events.slot_names[app.launcher.events.active_slot].clone();
            let current = app
                .launcher
                .events
                .slot_profiles
                .get(&slot)
                .cloned()
                .unwrap_or_else(|| app.config.legacy_visual_overrides.clone());
            match app.export_event_slot_to_disk(&slot, &current) {
                Ok(path) => {
                    app.launcher.events.status = Some(format!("Exported: {}", path.display()))
                }
                Err(err) => app.launcher.events.status = Some(err),
            }
        }
    });

    ui.horizontal_wrapped(|ui| {
        ui.label("Rename Slot:");
        ui.text_edit_singleline(&mut app.launcher.events.rename_input);
    });

    if app.launcher.events.active_slot != previous_slot {
        save_slot_by_index(app, previous_slot);
        load_active_slot_profile(app);
        sync_event_slots_into_config(app);
        app.request_settings_save();
    }
}

fn draw_slot_button(
    ui: &mut Ui,
    label: &str,
    size: [f32; 2],
    bg: egui::Color32,
    hover: egui::Color32,
    text: egui::Color32,
    border: egui::Color32,
) -> bool {
    ui.scope(|ui| {
        let visuals = &mut ui.style_mut().visuals;
        visuals.widgets.inactive.bg_fill = bg;
        visuals.widgets.inactive.bg_stroke = egui::Stroke::new(1.0, border);
        visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.0, text);
        visuals.widgets.hovered.bg_fill = hover;
        visuals.widgets.hovered.bg_stroke = egui::Stroke::new(1.0, text);
        visuals.widgets.hovered.fg_stroke = egui::Stroke::new(1.0, egui::Color32::WHITE);
        ui.add_sized(size, egui::Button::new(label)).clicked()
    })
    .inner
}

fn draw_master_controls(app: &mut OverlayState, ui: &mut Ui) {
    let mut changed = false;
    ui.horizontal_wrapped(|ui| {
        if ui
            .checkbox(&mut app.config.play_event_sounds, "Enable Events (Effects)")
            .changed()
        {
            changed = true;
        }
        let mut glow_enabled = app
            .config
            .legacy_visual_overrides
            .values()
            .any(|cfg| cfg.glow.unwrap_or(false));
        if ui.checkbox(&mut glow_enabled, "Enable Glow").changed() {
            for cfg in app.config.legacy_visual_overrides.values_mut() {
                cfg.glow = Some(glow_enabled);
            }
            app.launcher.events.status = Some(if glow_enabled {
                "Glow enabled for all events".to_owned()
            } else {
                "Glow disabled for all events".to_owned()
            });
            changed = true;
        }
        ui.label("Glow Color:");
        if ui.button("PICK").clicked() {
            for cfg in app.config.legacy_visual_overrides.values_mut() {
                cfg.glow_color = Some("#00f2ff".to_owned());
            }
            app.launcher.events.status = Some("Glow color set to #00f2ff".to_owned());
            changed = true;
        }
    });

    ui.horizontal_wrapped(|ui| {
        let queue_label = if app.config.event_queue_active {
            "QUEUE: ON"
        } else {
            "QUEUE: OFF"
        };
        if crate::launcher::theme::small_button(ui, queue_label).clicked() {
            app.config.event_queue_active = !app.config.event_queue_active;
            changed = true;
        }

        ui.label("If Queue is off or no time set (ms):");
        if ui
            .add(
                egui::DragValue::new(&mut app.config.event_global_duration_ms)
                    .speed(50)
                    .range(0..=60000),
            )
            .changed()
        {
            changed = true;
        }

        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if crate::launcher::theme::small_button(ui, "APPLY LAYOUT TO ALL").clicked() {
                if let Some(selected) = app.launcher.events.selected_event.as_ref() {
                    let key = selected.to_ascii_lowercase();
                    if let Some(source) = app.config.legacy_visual_overrides.get(&key).cloned() {
                        for cfg in app.config.legacy_visual_overrides.values_mut() {
                            cfg.x = source.x;
                            cfg.y = source.y;
                            cfg.width = source.width;
                            cfg.height = source.height;
                            cfg.centered = source.centered;
                            cfg.scale = source.scale;
                        }
                        app.launcher.events.status =
                            Some("Applied selected event layout to all entries".to_owned());
                        changed = true;
                    } else {
                        app.launcher.events.status =
                            Some("Select an event with saved layout first".to_owned());
                    }
                } else {
                    app.launcher.events.status = Some("Select an event first".to_owned());
                }
            }
        });
    });

    if changed {
        save_current_slot_profile(app);
        sync_event_slots_into_config(app);
        app.request_settings_save();
    }

    if let Some(msg) = &app.launcher.events.status {
        ui.label(msg);
    }
}

fn draw_event_category_grid(app: &mut OverlayState, ui: &mut Ui) {
    let categories: [(&str, &[&str]); 8] = [
        (
            "STANDARD",
            &[
                "Kill",
                "Headshot",
                "Assist",
                "Death",
                "Suicide",
                "Hitmarker",
                "Team Kill",
                "Team Kill Victim",
            ],
        ),
        (
            "VEHICLES",
            &[
                "Gunner Kill",
                "Vehicle Destruction",
                "Gunner Vehicle Destruction",
            ],
        ),
        (
            "STREAKS",
            &[
                "Squad Wiper",
                "Double Squad Wipe",
                "Squad Lead's Nightmare",
                "One Man Platoon",
            ],
        ),
        (
            "MULTI KILL",
            &[
                "Double Kill",
                "Multi Kill",
                "Mega Kill",
                "Ultra Kill",
                "Monster Kill",
                "Ludacris Kill",
                "Holy Shit",
            ],
        ),
        (
            "SPECIAL",
            &[
                "Bounty Kill",
                "Domination",
                "Revenge",
                "Killstreak Stop",
                "Nade Kill",
                "Knife Kill",
                "RoadKill",
                "Spitfire Kill",
            ],
        ),
        (
            "SUPPORT",
            &[
                "Revive Given",
                "Revive Taken",
                "Heal",
                "Resupply",
                "Repair",
                "Break Construction",
                "Mine Kill",
                "Squad Spawn",
                "Transport Assist",
                "Sunderer Spawn",
            ],
        ),
        (
            "OBJECTIVES",
            &["Point Control", "Base Capture", "Alert End", "Alert Win"],
        ),
        ("SYSTEM", &["Login TR", "Login NC", "Login VS", "Login NSO"]),
    ];

    let expandable: [(&str, &[&str]); 8] = [
        (
            "Kill",
            &[
                "Kill Infil",
                "Kill Light Assault",
                "Kill Medic",
                "Kill Engineer",
                "Kill Heavy",
                "Kill MAX",
            ],
        ),
        ("Death", &["Headshot Death", "Get RoadKilled"]),
        (
            "Vehicle Destruction",
            &[
                "Kill Flash",
                "Kill Sunderer",
                "Kill Lightning",
                "Kill Magrider",
                "Kill Vanguard",
                "Kill Prowler",
                "Kill Scythe",
                "Kill Reaver",
                "Kill Mosquito",
                "Kill Liberator",
                "Kill Galaxy",
                "Kill Valkyrie",
                "Kill Harasser",
                "Kill Ant",
                "Kill Colossus",
                "Kill Javelin",
                "Kill Dervish",
                "Kill Chimera",
                "Kill Corsair",
            ],
        ),
        (
            "Heal",
            &["Heal 50", "Heal 250", "Heal 500", "Heal 1000", "Heal 5000"],
        ),
        (
            "Revive Given",
            &[
                "Revive Given 5",
                "Revive Given 10",
                "Revive Given 25",
                "Revive Given 50",
                "Revive Given 100",
                "Revive Given 500",
            ],
        ),
        (
            "Resupply",
            &[
                "Resupply 50",
                "Resupply 100",
                "Resupply 250",
                "Resupply 500",
                "Resupply 1000",
            ],
        ),
        (
            "Repair",
            &[
                "Repair 50",
                "Repair 250",
                "Repair 500",
                "Repair 1000",
                "Repair 5000",
            ],
        ),
        ("Hitmarker", &["Headshot Hitmarker"]),
    ];
    let expand_map: HashMap<&str, &[&str]> = expandable.into_iter().collect();

    egui::ScrollArea::horizontal()
        .auto_shrink([false, false])
        .show(ui, |ui| {
            ui.horizontal_top(|ui| {
                for (category_name, items) in categories {
                    let card_width = estimate_category_width(category_name, items, &expand_map);
                    egui::Frame::group(ui.style()).show(ui, |ui| {
                        ui.push_id(category_name, |ui| {
                            ui.set_min_width(card_width);
                            ui.set_max_width(card_width);
                            ui.set_min_height(235.0);

                            ui.vertical(|ui| {
                                ui.label(
                                    RichText::new(category_name)
                                        .strong()
                                        .color(egui::Color32::from_rgb(0, 242, 255)),
                                );
                                ui.separator();

                                egui::ScrollArea::vertical()
                                    .id_source(("events_cat_scroll", category_name))
                                    .max_height(190.0)
                                    .auto_shrink([false, false])
                                    .show(ui, |ui| {
                                        ui.vertical(|ui| {
                                            for item in items {
                                                ui.push_id(item, |ui| {
                                                    if let Some(subitems) = expand_map.get(item) {
                                                        egui::CollapsingHeader::new(format!(
                                                            "{item} \u{25BE}"
                                                        ))
                                                        .id_source((
                                                            "events_header",
                                                            category_name,
                                                            item,
                                                        ))
                                                        .default_open(false)
                                                        .show(ui, |ui| {
                                                            for sub in *subitems {
                                                                let selected = app
                                                                    .launcher
                                                                    .events
                                                                    .selected_event
                                                                    .as_deref()
                                                                    == Some(*sub);
                                                                if ui
                                                                    .selectable_label(
                                                                        selected, *sub,
                                                                    )
                                                                    .clicked()
                                                                {
                                                                    app.launcher
                                                                        .events
                                                                        .selected_category =
                                                                        category_name.to_owned();
                                                                    app.launcher
                                                                        .events
                                                                        .selected_event =
                                                                        Some(sub.to_string());
                                                                }
                                                            }
                                                        });
                                                    } else {
                                                        let selected = app
                                                            .launcher
                                                            .events
                                                            .selected_event
                                                            .as_deref()
                                                            == Some(*item);
                                                        let resp = ui.add_sized(
                                                            [card_width - 18.0, 18.0],
                                                            egui::SelectableLabel::new(
                                                                selected, *item,
                                                            ),
                                                        );
                                                        if resp.clicked() {
                                                            app.launcher.events.selected_category =
                                                                category_name.to_owned();
                                                            app.launcher.events.selected_event =
                                                                Some(item.to_string());
                                                        }
                                                    }
                                                });
                                            }
                                        });
                                    });
                            });
                        });
                    });
                }
            });
        });
}

fn estimate_category_width(
    category_name: &str,
    items: &[&str],
    expand_map: &HashMap<&str, &[&str]>,
) -> f32 {
    let mut longest = category_name.len();
    for item in items {
        longest = longest.max(item.len());
        if let Some(subitems) = expand_map.get(item) {
            for sub in *subitems {
                longest = longest.max(sub.len());
            }
        }
    }
    let px = (longest as f32 * 7.0) + 34.0;
    px.clamp(170.0, 520.0)
}

fn draw_event_editor(app: &mut OverlayState, ui: &mut Ui) {
    let mut move_clicked = false;
    let mut save_clicked = false;
    let mut test_clicked = false;
    let mut changed = false;
    let mut test_event_name: Option<String> = None;

    egui::Frame::group(ui.style()).show(ui, |ui| {
        let editing_label = app
            .launcher
            .events
            .selected_event
            .as_deref()
            .map(|e| format!("EDITING: {}", e.to_ascii_uppercase()))
            .unwrap_or_else(|| "EDITING: NONE".to_owned());
        ui.label(
            RichText::new(editing_label)
                .strong()
                .color(egui::Color32::from_rgb(0, 255, 0)),
        );

        ui.columns(2, |columns| {
            columns[0].vertical(|ui| {
                if let Some(event_name) = &app.launcher.events.selected_event.clone() {
                    let storage_key = event_name.to_ascii_lowercase();
                    let mut cfg = app
                        .config
                        .legacy_visual_overrides
                        .get(&storage_key)
                        .cloned()
                        .unwrap_or_default();

                    ui.horizontal(|ui| {
                        ui.label("Image(s) (PNG/JPG):");
                        let mut filename = cfg.filename.clone().unwrap_or_default();
                        if ui.text_edit_singleline(&mut filename).changed() {
                            cfg.filename = if filename.is_empty() {
                                None
                            } else {
                                Some(filename)
                            };
                            changed = true;
                        }
                        if ui.button("...").clicked() {
                            if cfg.filename.is_none() {
                                cfg.filename = Some("Headshot.png".to_owned());
                                changed = true;
                            }
                        }
                        if ui.button("del").clicked() {
                            cfg.filename = None;
                            changed = true;
                        }
                    });

                    ui.horizontal(|ui| {
                        ui.label("Sound(s) (MP3/OGG):");
                        let mut snd = cfg.sound_filename.clone().unwrap_or_default();
                        if ui.text_edit_singleline(&mut snd).changed() {
                            cfg.sound_filename = if snd.is_empty() { None } else { Some(snd) };
                            changed = true;
                        }
                        if ui.button("...").clicked() {
                            if cfg.sound_filename.is_none() {
                                cfg.sound_filename = Some("Headshot.ogg".to_owned());
                                changed = true;
                            }
                        }
                        if ui.button("del").clicked() {
                            cfg.sound_filename = None;
                            changed = true;
                        }
                    });

                    ui.horizontal(|ui| {
                        ui.label("Scale:");
                        let mut scale = cfg.scale.unwrap_or(1.0);
                        if ui.add(Slider::new(&mut scale, 0.1..=3.0)).changed() {
                            cfg.scale = Some(scale);
                            changed = true;
                        }
                        ui.label(format!("{scale:.2}"));

                        ui.label("Duration (ms):");
                        let mut duration = cfg.duration_ms.unwrap_or(3000);
                        if ui
                            .add(
                                egui::DragValue::new(&mut duration)
                                    .speed(50)
                                    .range(0..=60000),
                            )
                            .changed()
                        {
                            cfg.duration_ms = Some(duration);
                            changed = true;
                        }
                    });

                    ui.horizontal(|ui| {
                        ui.label("Volume:");
                        let mut vol = cfg.sound_volume.unwrap_or(1.0).clamp(0.0, 1.0);
                        if ui.add(Slider::new(&mut vol, 0.0..=1.0)).changed() {
                            cfg.sound_volume = Some(vol);
                            changed = true;
                        }
                        ui.label(format!("{:.0}%", vol * 100.0));
                    });

                    let mut play_duplicate = cfg.play_duplicate.unwrap_or(true);
                    if ui.checkbox(&mut play_duplicate, "Play Duplicate").changed() {
                        cfg.play_duplicate = Some(play_duplicate);
                        changed = true;
                    }
                    let mut impact = cfg.impact.unwrap_or(false);
                    if ui.checkbox(&mut impact, "Impact Glitch").changed() {
                        cfg.impact = Some(impact);
                        changed = true;
                    }

                    ui.separator();
                    ui.horizontal(|ui| {
                        let move_label = if app.launcher.overlay_move_mode {
                            "STOP MOVE UI"
                        } else {
                            "MOVE UI"
                        };
                        if crate::launcher::theme::primary_button(ui, move_label).clicked() {
                            move_clicked = true;
                        }
                        if crate::launcher::theme::small_button(ui, "TEST PREVIEW").clicked() {
                            test_clicked = true;
                            test_event_name = app.launcher.events.selected_event.clone();
                        }
                        if crate::launcher::theme::success_button(ui, "SAVE EVENT").clicked() {
                            save_clicked = true;
                        }
                    });

                    if changed {
                        app.config.legacy_visual_overrides.insert(storage_key, cfg);
                        save_current_slot_profile(app);
                        sync_event_slots_into_config(app);
                        app.request_settings_save();
                    }
                } else {
                    ui.label("Select an event from the list to edit.");
                }
            });

            columns[1].vertical_centered(|ui| {
                let preview_label = app
                    .launcher
                    .events
                    .selected_event
                    .as_ref()
                    .map(|event_name| {
                        let key = event_name.to_ascii_lowercase();
                        let image = app
                            .config
                            .legacy_visual_overrides
                            .get(&key)
                            .and_then(|cfg| cfg.filename.as_deref())
                            .map(str::trim)
                            .filter(|value| !value.is_empty());
                        match image {
                            Some(filename) if app.asset_exists(filename) => "PREVIEW",
                            Some(_) => "IMG NOT FOUND",
                            None => "NO PREVIEW",
                        }
                    })
                    .unwrap_or("NO PREVIEW");
                ui.add_space(24.0);
                ui.group(|ui| {
                    ui.set_width(280.0);
                    ui.set_height(210.0);
                    ui.vertical_centered(|ui| {
                        ui.add_space(88.0);
                        ui.label(preview_label);
                    });
                });
            });
        });
    });

    if move_clicked {
        app.toggle_overlay_move_mode();
    }
    if test_clicked {
        app.trigger_event_preview(test_event_name.as_deref());
    }
    if save_clicked {
        let _ = app.save_settings_now();
    }
}

fn ensure_event_slots_initialized(app: &mut OverlayState) {
    if app.launcher.events.slot_names.is_empty() {
        if !app.config.event_slot_names.is_empty() {
            app.launcher.events.slot_names = app.config.event_slot_names.clone();
            app.launcher.events.slot_profiles = app.config.event_slot_profiles.clone();
            app.launcher.events.active_slot = app
                .config
                .event_active_slot
                .min(app.launcher.events.slot_names.len().saturating_sub(1));

            for name in app.launcher.events.slot_names.clone() {
                app.launcher
                    .events
                    .slot_profiles
                    .entry(name)
                    .or_insert_with(|| app.config.legacy_visual_overrides.clone());
            }
            load_active_slot_profile(app);
        } else {
            let name = "default".to_owned();
            app.launcher.events.slot_names.push(name.clone());
            app.launcher
                .events
                .slot_profiles
                .insert(name, app.config.legacy_visual_overrides.clone());
            app.launcher.events.active_slot = 0;
            sync_event_slots_into_config(app);
        }
    }
}

fn save_slot_by_index(app: &mut OverlayState, idx: usize) {
    if let Some(name) = app.launcher.events.slot_names.get(idx).cloned() {
        app.launcher
            .events
            .slot_profiles
            .insert(name, app.config.legacy_visual_overrides.clone());
        sync_event_slots_into_config(app);
    }
}

fn save_current_slot_profile(app: &mut OverlayState) {
    save_slot_by_index(app, app.launcher.events.active_slot);
}

fn load_active_slot_profile(app: &mut OverlayState) {
    if let Some(name) = app
        .launcher
        .events
        .slot_names
        .get(app.launcher.events.active_slot)
        .cloned()
    {
        if let Some(profile) = app.launcher.events.slot_profiles.get(&name).cloned() {
            app.config.legacy_visual_overrides = profile;
        }
    }
}

fn sync_event_slots_into_config(app: &mut OverlayState) {
    app.config.event_slot_names = app.launcher.events.slot_names.clone();
    app.config.event_active_slot = app.launcher.events.active_slot;
    app.config.event_slot_profiles = app.launcher.events.slot_profiles.clone();
}
