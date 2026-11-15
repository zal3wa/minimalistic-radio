import AppKit
import RadioCore
import SwiftUI

/// Statistics (Settings › Statistics › Show): listening time, song titles, stations, the longest session, the top
/// stations and artists, and the hours of the day, for this month, this year or everything. Counted in RadioCore
/// (summarizeStatistics) from statistics.json, which never leaves this Mac.
struct StatisticsPage: View {
    @ObservedObject var model: PanelModel
    @State private var period = StatisticsPeriod.month

    var body: some View {
        let summary = summarizeStatistics(model.statistics, period: period, now: Date())
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                PeriodSwitch(period: $period, labels: [(.all, L("All")), (.year, L("Year")), (.month, L("Month"))])
                    .frame(maxWidth: .infinity)
                if !model.controller.prefs.collectStatistics {
                    Text(L("Statistics are off. Nothing new is recorded."))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                if summary.isEmpty {
                    Text(L("Nothing here yet. Listen for a while and come back."))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 24)
                } else {
                    total(summary)
                    tiles(summary)
                    topStations(summary)
                    topArtists(summary)
                    hours(summary)
                    Button(L("Clear statistics"), action: confirmClear)
                        .buttonStyle(.link)
                        .padding(.top, 4)
                }
            }
            .padding(EdgeInsets(top: 16, leading: 20, bottom: 20, trailing: 20))
        }
    }

    // MARK: - Parts

    private func total(_ summary: StatisticsSummary) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(L("Listening time"))
                Spacer()
                Text(periodLabel(summary))
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
            Text(formatDuration(summary.total, L))
                .font(.system(size: 28, weight: .bold))
            Text(L("≈ {0} a day").replacingOccurrences(of: "{0}", with: formatDuration(summary.perDay, L)))
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .statisticsCard()
    }

    /// Three equal tiles; the labels at the top and the values at the bottom, so the values stay in one row even if a
    /// label takes two lines.
    private func tiles(_ summary: StatisticsSummary) -> some View {
        HStack(spacing: 8) {
            tile(L("Song titles"), number(summary.songs))
            tile(L("Stations"), number(summary.stations))
            tile(L("Longest"), formatDuration(summary.longest, L))
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func tile(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Text(value)
                .font(.system(size: 15, weight: .semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .statisticsCard()
    }

    private func topStations(_ summary: StatisticsSummary) -> some View {
        let longest = summary.topStations.first?.time ?? 1
        return VStack(alignment: .leading, spacing: 8) {
            header(L("Top stations"))
            VStack(spacing: 0) {
                ForEach(Array(summary.topStations.enumerated()), id: \.offset) { index, item in
                    if index > 0 { Divider() }
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 10) {
                            LogoView(logos: model.logos, url: model.station(url: item.url, name: item.name)?.logo, size: 28)
                            Text(item.name).lineLimit(1)
                            Spacer(minLength: 4)
                            Text(formatDuration(item.time, L))
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        GeometryReader { space in
                            RoundedRectangle(cornerRadius: 3)
                                .fill(Color.accentColor)
                                .frame(width: max(6, space.size.width * min(1, item.time / max(longest, 1))))
                        }
                        .frame(height: 6)
                        .padding(.leading, 38)
                    }
                    .padding(.vertical, 9)
                }
            }
            .padding(.horizontal, 12)
            .statisticsCard()
        }
    }

    private func topArtists(_ summary: StatisticsSummary) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                header(L("Top artists"))
                Text(L("From song titles sent by the stations · {0} of listening time")
                    .replacingOccurrences(of: "{0}", with: percent(summary.titlesShare)))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            VStack(spacing: 0) {
                if summary.showsArtists {
                    ForEach(Array(summary.topArtists.enumerated()), id: \.offset) { index, artist in
                        if index > 0 { Divider() }
                        HStack(spacing: 10) {
                            Text(number(index + 1))
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .frame(width: 14, alignment: .trailing)
                            Text(artist.name).lineLimit(1)
                            Spacer(minLength: 4)
                            Text(plays(artist.plays))
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        .frame(minHeight: 36)
                    }
                } else {
                    Text(L("Not enough song titles yet"))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, minHeight: 36, alignment: .leading)
                }
            }
            .padding(.horizontal, 12)
            .statisticsCard()
        }
    }

    private func hours(_ summary: StatisticsSummary) -> some View {
        let most = max(summary.hours.max() ?? 0, 1)
        return VStack(alignment: .leading, spacing: 8) {
            header(L("When you listen"))
            VStack(alignment: .leading, spacing: 6) {
                if let peak = summary.peakHour {
                    Text(L("Most often {0}").replacingOccurrences(of: "{0}", with: hourRange(peak)))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                HStack(alignment: .bottom, spacing: 2) {
                    ForEach(0..<24, id: \.self) { hour in
                        RoundedRectangle(cornerRadius: 2)
                            .fill(Color.accentColor)
                            .frame(height: CGFloat(60 * summary.hours[hour] / most))
                            .frame(maxWidth: .infinity)
                    }
                }
                .frame(height: 64, alignment: .bottom)
                .overlay(alignment: .bottom) { Rectangle().fill(Color.primary.opacity(0.12)).frame(height: 1) }
                HStack {
                    ForEach(["00", "06", "12", "18", "24"], id: \.self) { label in
                        if label != "00" { Spacer() }
                        Text(label)
                    }
                }
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(.secondary)
            }
            .padding(EdgeInsets(top: 12, leading: 14, bottom: 8, trailing: 14))
            .statisticsCard()
        }
    }

    private func header(_ text: String) -> some View {
        Text(text).font(.headline).padding(.top, 6)
    }

    // MARK: - Words and numbers in the UI's language

    private var locale: Locale { Locale(identifier: localizer.language) }

    /// "November 2026", "2026" or "Since 2 March 2025".
    private func periodLabel(_ summary: StatisticsSummary) -> String {
        let formatter = DateFormatter()
        formatter.locale = locale
        switch period {
        case .month:
            formatter.setLocalizedDateFormatFromTemplate("LLLLyyyy")
            return formatter.string(from: Date())
        case .year:
            formatter.setLocalizedDateFormatFromTemplate("yyyy")
            return formatter.string(from: Date())
        case .all:
            formatter.dateStyle = .long
            formatter.timeStyle = .none
            return L("Since {0}").replacingOccurrences(of: "{0}", with: formatter.string(from: summary.start ?? Date()))
        }
    }

    private func number(_ value: Int) -> String {
        let formatter = NumberFormatter()
        formatter.locale = locale
        formatter.numberStyle = .decimal
        return formatter.string(from: NSNumber(value: value)) ?? String(value)
    }

    private func percent(_ share: Double) -> String {
        let formatter = NumberFormatter()
        formatter.locale = locale
        formatter.numberStyle = .percent
        formatter.maximumFractionDigits = 0
        return formatter.string(from: NSNumber(value: share)) ?? "\(Int((share * 100).rounded()))%"
    }

    /// "1 play", "14 plays": the catalogues have no plural forms, so the translations read right with any number.
    private func plays(_ count: Int) -> String {
        count == 1 ? L("1 play") : L("{0} plays").replacingOccurrences(of: "{0}", with: number(count))
    }

    /// "20:00–21:00" (or "8:00 – 9:00 PM"), in the UI language's time format.
    private func hourRange(_ hour: Int) -> String {
        let formatter = DateIntervalFormatter()
        formatter.locale = locale
        formatter.dateTemplate = "jm"
        let start = Calendar.current.date(bySettingHour: hour, minute: 0, second: 0, of: Date()) ?? Date()
        return formatter.string(from: start, to: start.addingTimeInterval(3600))
    }

    // MARK: - Clearing

    /// "Clear statistics", after a confirmation (a sheet on the panel, so the panel stays open behind it).
    private func confirmClear() {
        let alert = NSAlert()
        alert.messageText = L("Clear statistics?")
        alert.informativeText = L("All listening statistics on this computer will be deleted. The song history stays.")
        alert.alertStyle = .warning
        alert.addButton(withTitle: L("Clear statistics")).hasDestructiveAction = true
        alert.addButton(withTitle: L("Cancel"))
        let model = self.model
        let clear = {
            if model.sampleStatistics != nil { model.sampleStatistics = StatisticsLog() } else { model.controller.clearStatistics() }
            model.refresh()
        }
        if let window = AppDelegate.shared?.panel?.window {
            alert.beginSheetModal(for: window) { response in
                if response == .alertFirstButtonReturn { clear() }
            }
        } else if alert.runModal() == .alertFirstButtonReturn {
            clear()
        }
    }
}

/// All / Year / Month: the Mac's segmented control, its three segments equally wide across the page.
struct PeriodSwitch: NSViewRepresentable {
    @Binding var period: StatisticsPeriod
    let labels: [(StatisticsPeriod, String)]

    func makeNSView(context: Context) -> NSSegmentedControl {
        let control = NSSegmentedControl(labels: labels.map(\.1), trackingMode: .selectOne, target: context.coordinator,
                                         action: #selector(Coordinator.changed(_:)))
        control.segmentDistribution = .fillEqually
        control.setContentHuggingPriority(.defaultLow, for: .horizontal)
        return control
    }

    func updateNSView(_ control: NSSegmentedControl, context: Context) {
        context.coordinator.parent = self
        for (index, label) in labels.enumerated() where control.label(forSegment: index) != label.1 {
            control.setLabel(label.1, forSegment: index)
        }
        control.selectedSegment = labels.firstIndex { $0.0 == period } ?? 0
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    final class Coordinator: NSObject {
        var parent: PeriodSwitch

        init(_ parent: PeriodSwitch) {
            self.parent = parent
        }

        @objc func changed(_ control: NSSegmentedControl) {
            guard parent.labels.indices.contains(control.selectedSegment) else { return }
            parent.period = parent.labels[control.selectedSegment].0
        }
    }
}

private extension View {
    /// A rounded box like the settings' groups.
    func statisticsCard() -> some View {
        background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Color.primary.opacity(0.05)))
    }
}
