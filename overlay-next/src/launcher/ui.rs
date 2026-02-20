use eframe::egui::{self, Ui};

use super::{LauncherTab, TopLevelTab};
use crate::app::OverlayState;

pub fn draw_launcher(app: &mut OverlayState, ctx: &egui::Context) {
    egui::SidePanel::left("launcher_sidebar")
        .frame(egui::Frame::none().fill(crate::launcher::theme::COLOR_PANEL))
        .exact_width(236.0)
        .show(ctx, |ui| {
            ui.add_space(12.0);
            ui.label(
                egui::RichText::new("Better Planetside")
                    .size(16.0)
                    .strong()
                    .color(crate::launcher::theme::COLOR_TEXT),
            );
            ui.add_space(10.0);
            ui.separator();
            ui.add_space(8.0);

            top_button(ui, app, "Dashboard", TopLevelTab::Dashboard);
            top_button(ui, app, "Launcher", TopLevelTab::Launcher);
            top_button(ui, app, "Characters", TopLevelTab::Characters);
            top_button(ui, app, "Overlay", TopLevelTab::Overlay);
            top_button(ui, app, "Settings", TopLevelTab::Settings);
        });

    egui::CentralPanel::default()
        .frame(
            egui::Frame::none()
                .fill(crate::launcher::theme::COLOR_BG)
                .inner_margin(egui::Margin::same(14.0)),
        )
        .show(ctx, |ui| {
            ui.add_space(2.0);
            match app.launcher.active_top_tab {
                TopLevelTab::Dashboard => {
                    egui::ScrollArea::vertical()
                        .auto_shrink([false, false])
                        .show(ui, |ui| super::dashboard::draw(app, ui));
                }
                TopLevelTab::Launcher => {
                    egui::ScrollArea::vertical()
                        .auto_shrink([false, false])
                        .show(ui, |ui| super::game_launcher::draw(app, ui));
                }
                TopLevelTab::Characters => {
                    egui::ScrollArea::vertical()
                        .auto_shrink([false, false])
                        .show(ui, |ui| super::characters_page::draw(app, ui));
                }
                TopLevelTab::Overlay => draw_overlay_pages(app, ui),
                TopLevelTab::Settings => {
                    egui::ScrollArea::vertical()
                        .auto_shrink([false, false])
                        .show(ui, |ui| super::settings_page::draw(app, ui));
                }
            }
        });
}

fn top_button(ui: &mut Ui, app: &mut OverlayState, text: &str, tab: TopLevelTab) {
    if crate::launcher::theme::custom_tab_button(ui, text, app.launcher.active_top_tab == tab)
        .clicked()
    {
        app.launcher.active_top_tab = tab;
    }
}

fn draw_overlay_pages(app: &mut OverlayState, ui: &mut Ui) {
    crate::launcher::theme::card_frame().show(ui, |ui| {
        ui.horizontal_wrapped(|ui| {
            ui.spacing_mut().item_spacing.x = 6.0;
            ui.spacing_mut().item_spacing.y = 6.0;
            draw_top_nav_button(ui, &mut app.launcher.active_tab, LauncherTab::Identity);
            draw_top_nav_button(ui, &mut app.launcher.active_tab, LauncherTab::Events);
            draw_top_nav_button(ui, &mut app.launcher.active_tab, LauncherTab::Killstreak);
            draw_top_nav_button(ui, &mut app.launcher.active_tab, LauncherTab::Crosshair);
            draw_top_nav_button(ui, &mut app.launcher.active_tab, LauncherTab::Stats);
            draw_top_nav_button(ui, &mut app.launcher.active_tab, LauncherTab::Killfeed);
            draw_top_nav_button(ui, &mut app.launcher.active_tab, LauncherTab::Voice);
            draw_top_nav_button(ui, &mut app.launcher.active_tab, LauncherTab::Twitch);
            draw_top_nav_button(ui, &mut app.launcher.active_tab, LauncherTab::Obs);
        });
    });
    ui.separator();

    if app.launcher.active_tab == LauncherTab::Events {
        super::events::draw(app, ui);
        return;
    }

    egui::ScrollArea::vertical().show(ui, |ui| match app.launcher.active_tab {
        LauncherTab::Identity => super::identity::draw(app, ui),
        LauncherTab::Events => {}
        LauncherTab::Killstreak => super::killstreak::draw(app, ui),
        LauncherTab::Crosshair => super::crosshair::draw(app, ui),
        LauncherTab::Stats => super::stats::draw(app, ui),
        LauncherTab::Killfeed => super::killfeed::draw(app, ui),
        LauncherTab::Voice => super::voice::draw(app, ui),
        LauncherTab::Twitch => super::twitch::draw(app, ui),
        LauncherTab::Obs => super::obs::draw(app, ui),
    });
}

fn draw_top_nav_button(ui: &mut Ui, active: &mut LauncherTab, tab: LauncherTab) {
    if crate::launcher::theme::top_nav_button(ui, tab.label(), *active == tab).clicked() {
        *active = tab;
    }
}
