import CoreGraphics

/// Where the panel (or the station card) opens, in screen coordinates (origin at the bottom left):
/// just under the menu bar icon and centred on it, kept 8 pt inside the visible screen. Without the icon (hidden
/// behind a MacBook's notch, or the panel opened from Spotlight) it opens at the top right.
public func panelOrigin(anchor: CGRect?, visibleFrame: CGRect, size: CGSize) -> CGPoint {
    let margin: CGFloat = 8
    let right = visibleFrame.maxX - margin - size.width
    let highest = visibleFrame.maxY - margin
    guard let anchor else { return CGPoint(x: right, y: highest - size.height) }
    let x = min(max(anchor.midX - size.width / 2, visibleFrame.minX + margin), right)
    let top = min(anchor.minY - 4, highest)
    return CGPoint(x: x, y: top - size.height)
}
