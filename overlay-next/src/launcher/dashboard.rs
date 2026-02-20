use eframe::egui::{self, Align, Color32, Layout, Pos2, Rect, RichText, Ui};

use crate::app::OverlayState;
use crate::launcher::{DashboardSortColumn, DashboardSortState};

const DASHBOARD_SERVERS: [(&str, &str); 4] = [
    ("Wainwright (EU)", "10"),
    ("Osprey (US)", "1"),
    ("SolTech (Asia)", "40"),
    ("Jaeger (Events)", "19"),
];

fn world_name(world_id: &str) -> &'static str {
    let normalized = canonical_world_id(world_id);
    DASHBOARD_SERVERS
        .iter()
        .find(|(_, id)| *id == normalized)
        .map(|(name, _)| *name)
        .unwrap_or("Unknown")
}

fn canonical_world_id(world_id: &str) -> &str {
    match world_id {
        "13" => "10",
        "17" => "1",
        _ => world_id,
    }
}

pub fn draw(app: &mut OverlayState, ui: &mut Ui) {
    ui.spacing_mut().item_spacing.y = 10.0;

    if app.launcher.dashboard.selected_world_id.trim().is_empty() {
        app.launcher.dashboard.selected_world_id = if app.config.world_id.trim().is_empty() {
            "10".to_owned()
        } else {
            app.config.world_id.clone()
        };
    }
    let selected_world_id = app.launcher.dashboard.selected_world_id.clone();
    let selected_server_name = world_name(&selected_world_id).to_owned();
    let tr_rows = collect_faction_rows(app, &selected_world_id, "TR");
    let nc_rows = collect_faction_rows(app, &selected_world_id, "NC");
    let vs_rows = collect_faction_rows(app, &selected_world_id, "VS");
    let tr = tr_rows.len();
    let nc = nc_rows.len();
    let vs = vs_rows.len();
    let total = tr + nc + vs;
    push_graph_history(app, total as u32, tr as u32, nc as u32, vs as u32);
    let total_f = total.max(1) as f32;

    crate::launcher::theme::card_frame().show(ui, |ui| {
        ui.horizontal(|ui| {
            let kd_label = if app.config.kd_mode_revive {
                "KD MODE: REVIVE"
            } else {
                "KD MODE: REAL"
            };
            let kd_response = ui.scope(|ui| {
                let visuals = &mut ui.style_mut().visuals;
                visuals.widgets.inactive.fg_stroke = egui::Stroke::new(1.0, Color32::from_rgb(0, 255, 0));
                visuals.widgets.hovered.fg_stroke = egui::Stroke::new(1.0, Color32::from_rgb(0, 255, 0));
                visuals.widgets.active.fg_stroke = egui::Stroke::new(1.0, Color32::from_rgb(0, 255, 0));
                ui.add_sized(
                    [120.0, 24.0],
                    egui::Button::new(RichText::new(kd_label).size(10.0).strong()),
                )
            }).inner;
            if kd_response.clicked() {
                app.config.kd_mode_revive = !app.config.kd_mode_revive;
                app.request_settings_save();
            }
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                let mut selected_name = selected_server_name.clone();
                egui::ComboBox::from_id_source("dashboard_server_combo")
                    .width(200.0)
                    .selected_text(&selected_name)
                    .show_ui(ui, |ui| {
                        for (name, _) in DASHBOARD_SERVERS {
                            ui.selectable_value(&mut selected_name, name.to_owned(), name);
                        }
                    });
                ui.label(
                    RichText::new("SERVER:")
                        .small()
                        .strong()
                        .color(Color32::from_rgb(220, 220, 220)),
                );
                if selected_name != selected_server_name {
                    if let Some((_, world_id)) = DASHBOARD_SERVERS
                        .iter()
                        .find(|(name, _)| *name == selected_name)
                    {
                        app.launcher.dashboard.selected_world_id = (*world_id).to_owned();
                        app.config.world_id = (*world_id).to_owned();
                        app.request_settings_save();
                    }
                }
            });
        });
        ui.add_space(8.0);
        draw_population_graph(ui, app.launcher.dashboard.graph_show_factions, app, 150.0);
    });

    ui.add_space(8.0);
    crate::launcher::theme::card_frame().show(ui, |ui| {
        let spacing = 15.0;
        let col_width = ((ui.available_width().max(0.0) - spacing * 2.0) / 3.0).max(0.0);
        let mode_row_w = ui.available_width().max(0.0);
        let (mode_rect, _) = ui.allocate_exact_size(egui::vec2(mode_row_w, 24.0), egui::Sense::hover());
        ui.allocate_ui_at_rect(mode_rect, |ui| {
            ui.horizontal(|ui| {
                let graph_label = if app.launcher.dashboard.graph_show_factions {
                    "MODE: FACTIONS"
                } else {
                    "MODE: ALL PLAYERS"
                };
                let mode_clicked = ui.scope(|ui| {
                    let visuals = &mut ui.style_mut().visuals;
                    visuals.widgets.inactive.fg_stroke =
                        egui::Stroke::new(1.0, Color32::from_rgb(0, 242, 255));
                    visuals.widgets.hovered.fg_stroke =
                        egui::Stroke::new(1.0, Color32::from_rgb(0, 242, 255));
                    visuals.widgets.active.fg_stroke =
                        egui::Stroke::new(1.0, Color32::from_rgb(0, 242, 255));
                    ui.add_sized(
                        [150.0, 24.0],
                        egui::Button::new(RichText::new(graph_label).size(10.0).strong()),
                    )
                    .clicked()
                }).inner;
                if mode_clicked {
                    app.launcher.dashboard.graph_show_factions =
                        !app.launcher.dashboard.graph_show_factions;
                }
            });
        });

        let total_row_w = ui.available_width().max(0.0);
        let (total_rect, _) =
            ui.allocate_exact_size(egui::vec2(total_row_w, 20.0), egui::Sense::hover());
        ui.painter().text(
            total_rect.center(),
            egui::Align2::CENTER_CENTER,
            format!("Total Players: {total}"),
            egui::FontId::new(14.0, egui::FontFamily::Proportional),
            Color32::from_rgb(225, 225, 225),
        );
        ui.add_space(4.0);

        ui.horizontal_top(|ui| {
            ui.spacing_mut().item_spacing.x = spacing;
            draw_faction_panel(
                ui,
                col_width,
                "TR",
                Color32::from_rgb(222, 11, 11),
                tr,
                total_f,
                &tr_rows,
                &mut app.launcher.dashboard.tr_sort,
            );
            draw_faction_panel(
                ui,
                col_width,
                "NC",
                Color32::from_rgb(0, 123, 255),
                nc,
                total_f,
                &nc_rows,
                &mut app.launcher.dashboard.nc_sort,
            );
            draw_faction_panel(
                ui,
                col_width,
                "VS",
                Color32::from_rgb(157, 0, 255),
                vs,
                total_f,
                &vs_rows,
                &mut app.launcher.dashboard.vs_sort,
            );
        });
    });

    ui.add_space(4.0);
    ui.horizontal(|ui| {
        ui.label(
            RichText::new(format!("Server: {selected_server_name}"))
                .small()
                .color(Color32::from_rgb(150, 150, 150)),
        );
        ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
            ui.label(
                RichText::new(format!("UNIQUE DB: {}", app.db_player_count))
                    .small()
                    .color(Color32::from_rgb(150, 150, 150)),
            );
            ui.separator();
            ui.label(
                RichText::new("Last Update: Live via Census")
                    .small()
                    .color(Color32::from_rgb(150, 150, 150)),
            );
        });
    });
}

fn collect_faction_rows(app: &OverlayState, world_id: &str, faction: &str) -> Vec<String> {
    let selected_world = canonical_world_id(world_id).to_owned();
    let mut rows = app
        .active_players
        .iter()
        .filter(|(_, player)| canonical_world_id(player.world_id.as_str()) == selected_world)
        .filter(|(_, player)| player.faction == faction)
        .map(|(character_id, _)| {
            let name = app
                .name_cache
                .get(character_id)
                .cloned()
                .or_else(|| {
                    app.characters
                        .iter()
                        .find(|entry| &entry.character_id == character_id)
                        .map(|entry| entry.name.clone())
                })
                .unwrap_or_else(|| character_id.clone());
            let outfit = app
                .outfit_cache
                .get(character_id)
                .filter(|tag| !tag.trim().is_empty())
                .map(|tag| format!("[{tag}] "))
                .unwrap_or_default();
            format!("{outfit}{name}")
        })
        .collect::<Vec<_>>();
    rows.sort_by_key(|name| name.to_ascii_lowercase());
    rows
}

fn draw_faction_panel(
    ui: &mut Ui,
    width: f32,
    faction: &str,
    color: Color32,
    count: usize,
    total_f: f32,
    rows: &[String],
    sort_state: &mut DashboardSortState,
) {
    ui.vertical(|ui| {
        ui.set_min_width(width);
        ui.set_max_width(width);
        ui.spacing_mut().item_spacing.y = 5.0;
        egui::Frame::none()
            .inner_margin(egui::Margin::symmetric(5.0, 5.0))
            .show(ui, |ui| {
                draw_faction_column(ui, faction, color, count, total_f, rows, sort_state)
            });
    });
}

fn draw_faction_column(
    ui: &mut Ui,
    faction: &str,
    color: Color32,
    count: usize,
    total_f: f32,
    rows: &[String],
    sort_state: &mut DashboardSortState,
) {
    let pct = (count as f32 / total_f * 100.0).clamp(0.0, 100.0);
    ui.vertical(|ui| {
        let table_width = ui.available_width().max(0.0);
        ui.vertical_centered(|ui| {
            ui.label(RichText::new(faction).strong().size(16.0).color(color));
            ui.label(
                RichText::new(format!("{pct:.1}%"))
                    .strong()
                    .size(20.0)
                    .color(Color32::WHITE),
            );
            ui.label(
                RichText::new(format!("{count} Players"))
                    .size(10.0)
                .color(Color32::from_rgb(136, 136, 136)),
            );
        });
        ui.add_sized(
            [table_width, 10.0],
            egui::ProgressBar::new((count as f32 / total_f).clamp(0.0, 1.0))
                .fill(color)
                .text(""),
        );
        ui.add_space(4.0);
        draw_player_table(ui, faction, rows, table_width, sort_state);
    });
}

fn draw_player_table(
    ui: &mut Ui,
    faction: &str,
    rows: &[String],
    table_width: f32,
    sort_state: &mut DashboardSortState,
) {
    let frame_padding_x = 0.0;
    let col_gap = 0.0;
    let content_width = (table_width - frame_padding_x * 2.0).max(150.0);
    let usable_width = (content_width - col_gap * 6.0).max(120.0);
    let stat_col = ((usable_width * 0.54) / 6.0).clamp(18.0, 35.0);
    let player_col = (usable_width - stat_col * 6.0).max(80.0);
    let columns = [
        (DashboardSortColumn::Player, "PLAYER", player_col),
        (DashboardSortColumn::K, "K", stat_col),
        (DashboardSortColumn::Kpm, "KPM", stat_col),
        (DashboardSortColumn::D, "D", stat_col),
        (DashboardSortColumn::A, "A", stat_col),
        (DashboardSortColumn::Kd, "K/D", stat_col),
        (DashboardSortColumn::Kda, "KDA", stat_col),
    ];
    let mut sorted_rows = rows.to_vec();
    if sort_state.column == DashboardSortColumn::Player {
        sorted_rows.sort_by_key(|name| name.to_ascii_lowercase());
        if !sort_state.ascending {
            sorted_rows.reverse();
        }
    }

    ui.set_min_width(table_width);
    ui.set_max_width(table_width);
    {
        egui::Frame::none()
            .fill(Color32::from_rgb(10, 10, 10))
            .stroke(egui::Stroke::new(1.0, Color32::from_rgb(26, 26, 26)))
            .inner_margin(egui::Margin::symmetric(frame_padding_x, 0.0))
            .show(ui, |ui| {
                ui.spacing_mut().item_spacing.x = col_gap;
                ui.horizontal(|ui| {
                    for (column, label, width) in columns {
                        let active = sort_state.column == column;
                        let response = draw_table_header_cell(ui, width, label, active, 22.0);
                        if response.clicked() {
                            if sort_state.column == column {
                                sort_state.ascending = !sort_state.ascending;
                            } else {
                                sort_state.column = column;
                                sort_state.ascending = false;
                            }
                        }
                    }
                });
            });
        egui::Frame::none()
            .fill(Color32::from_rgb(42, 42, 42))
            .inner_margin(egui::Margin::same(0.0))
            .show(ui, |ui| {
                ui.set_min_height(300.0);
                egui::ScrollArea::vertical()
                    .id_source(egui::Id::new("dashboard_faction_table").with(faction))
                    .auto_shrink([false, false])
                    .show(ui, |ui| {
                        for name in sorted_rows.iter().take(15) {
                            ui.horizontal(|ui| {
                                ui.spacing_mut().item_spacing.x = col_gap;
                                ui.add_sized(
                                    [player_col, 18.0],
                                    egui::Label::new(
                                        RichText::new(name)
                                            .small()
                                            .color(Color32::from_rgb(220, 220, 220)),
                                    ),
                                );
                                for _ in 0..6 {
                                    ui.allocate_ui_with_layout(
                                        egui::vec2(stat_col, 18.0),
                                        Layout::centered_and_justified(egui::Direction::LeftToRight),
                                        |ui| {
                                            ui.label(
                                                RichText::new("-")
                                                    .small()
                                                    .color(Color32::from_rgb(150, 150, 150)),
                                            );
                                        },
                                    );
                                }
                            });
                            ui.add_space(2.0);
                        }
                    });
            });
    }
}

fn draw_table_header_cell(
    ui: &mut Ui,
    width: f32,
    label: &str,
    active: bool,
    height: f32,
) -> egui::Response {
    let (rect, response) =
        ui.allocate_exact_size(egui::vec2(width, height), egui::Sense::click());
    let bg = if response.is_pointer_button_down_on() {
        Color32::from_rgb(24, 24, 24)
    } else if response.hovered() {
        Color32::from_rgb(18, 18, 18)
    } else {
        Color32::from_rgb(10, 10, 10)
    };
    let stroke = if active {
        egui::Stroke::new(1.0, Color32::from_rgb(0, 242, 255))
    } else {
        egui::Stroke::new(1.0, Color32::from_rgb(26, 26, 26))
    };
    ui.painter().rect(rect.shrink(0.5), 0.0, bg, stroke);
    ui.painter().text(
        rect.center(),
        egui::Align2::CENTER_CENTER,
        label,
        egui::FontId::new(10.0, egui::FontFamily::Proportional),
        if active {
            Color32::from_rgb(0, 242, 255)
        } else {
            Color32::from_rgb(136, 136, 136)
        },
    );
    response
}

fn push_graph_history(app: &mut OverlayState, total: u32, tr: u32, nc: u32, vs: u32) {
    let now = std::time::Instant::now();
    if now
        .duration_since(app.launcher.dashboard.last_history_sample)
        .as_secs_f32()
        < 1.0
    {
        return;
    }
    app.launcher.dashboard.last_history_sample = now;
    push_history_point(&mut app.launcher.dashboard.pop_history, total);
    push_history_point(&mut app.launcher.dashboard.tr_history, tr);
    push_history_point(&mut app.launcher.dashboard.nc_history, nc);
    push_history_point(&mut app.launcher.dashboard.vs_history, vs);
}

fn push_history_point(history: &mut Vec<u32>, value: u32) {
    history.push(value);
    if history.len() > 100 {
        history.remove(0);
    }
}

fn draw_population_graph(ui: &mut Ui, show_factions: bool, app: &OverlayState, height: f32) {
    let desired_size = egui::vec2(ui.available_width(), height);
    let (rect, _) = ui.allocate_exact_size(desired_size, egui::Sense::hover());
    let painter = ui.painter_at(rect);
    painter.rect_filled(rect, 2.0, Color32::from_rgb(20, 20, 20));
    painter.rect_stroke(
        rect,
        2.0,
        egui::Stroke::new(1.0, Color32::from_rgb(51, 51, 51)),
    );

    let datasets: Vec<(&[u32], Color32)> = if show_factions {
        vec![
            (
                &app.launcher.dashboard.pop_history,
                Color32::from_rgb(0, 242, 255),
            ),
            (
                &app.launcher.dashboard.tr_history,
                Color32::from_rgb(222, 11, 11),
            ),
            (
                &app.launcher.dashboard.nc_history,
                Color32::from_rgb(0, 123, 255),
            ),
            (
                &app.launcher.dashboard.vs_history,
                Color32::from_rgb(157, 0, 255),
            ),
        ]
    } else {
        vec![(
            &app.launcher.dashboard.pop_history,
            Color32::from_rgb(0, 242, 255),
        )]
    };
    let max_val = datasets
        .iter()
        .flat_map(|(series, _)| series.iter().copied())
        .max()
        .unwrap_or(100)
        .max(100) as f32
        * 1.1;
    draw_grid(&painter, rect, max_val);
    for (series, color) in datasets {
        draw_series(&painter, rect, series, max_val, color);
    }
}

fn draw_grid(painter: &egui::Painter, rect: Rect, max_val: f32) {
    let steps = 4;
    for i in 1..=steps {
        let t = i as f32 / steps as f32;
        let y = rect.bottom() - t * rect.height();
        let value = (max_val * t).round() as i32;
        painter.line_segment(
            [Pos2::new(rect.left(), y), Pos2::new(rect.right(), y)],
            egui::Stroke::new(1.0, Color32::from_rgb(40, 40, 40)),
        );
        painter.text(
            Pos2::new(rect.left() + 4.0, y - 12.0),
            egui::Align2::LEFT_TOP,
            value.to_string(),
            egui::FontId::monospace(10.0),
            Color32::from_rgb(120, 120, 120),
        );
    }
}

fn draw_series(painter: &egui::Painter, rect: Rect, series: &[u32], max_val: f32, color: Color32) {
    if series.len() < 2 {
        return;
    }
    let width = rect.width().max(1.0);
    let mut points = Vec::with_capacity(series.len());
    let denom = (series.len() - 1) as f32;
    for (idx, value) in series.iter().enumerate() {
        let x = rect.left() + (idx as f32 / denom) * width;
        let normalized = (*value as f32 / max_val).clamp(0.0, 1.0);
        let y = rect.bottom() - normalized * rect.height();
        points.push(Pos2::new(x, y));
    }
    painter.add(egui::Shape::line(points, egui::Stroke::new(2.0, color)));
}
