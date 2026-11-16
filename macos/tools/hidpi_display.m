// A 2× screen for the README and landing page pictures on CI (.github/workflows/macos.yml): GitHub's Mac runners
// have one 1× display, so the pictures taken from the screen (the menus) would be 1×. This adds a virtual HiDPI display
// (1440×900 points, 2880×1800 pixels) with CoreGraphics' virtual display classes, makes it the main display (the
// menu bar moves there), and keeps it until it is stopped. Not part of the app.
//
// clang -fobjc-arc -framework Foundation -framework CoreGraphics macos/tools/hidpi_display.m -o hidpi_display

#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>

@class CGVirtualDisplay;

@interface CGVirtualDisplayDescriptor : NSObject
@property (retain, nonatomic) dispatch_queue_t queue;
@property (retain, nonatomic) NSString *name;
@property (nonatomic) unsigned int maxPixelsHigh;
@property (nonatomic) unsigned int maxPixelsWide;
@property (nonatomic) CGSize sizeInMillimeters;
@property (nonatomic) unsigned int serialNum;
@property (nonatomic) unsigned int productID;
@property (nonatomic) unsigned int vendorID;
@property (copy, nonatomic) void (^terminationHandler)(id, CGVirtualDisplay *);
@end

@interface CGVirtualDisplayMode : NSObject
- (instancetype)initWithWidth:(unsigned int)width height:(unsigned int)height refreshRate:(double)refreshRate;
@end

@interface CGVirtualDisplaySettings : NSObject
@property (retain, nonatomic) NSArray *modes;
@property (nonatomic) unsigned int hiDPI;
@end

@interface CGVirtualDisplay : NSObject
@property (readonly, nonatomic) CGDirectDisplayID displayID;
- (instancetype)initWithDescriptor:(CGVirtualDisplayDescriptor *)descriptor;
- (BOOL)applySettings:(CGVirtualDisplaySettings *)settings;
@end

static const unsigned int pointsWide = 1440, pointsHigh = 900;

int main(void) {
    @autoreleasepool {
        CGDirectDisplayID real = CGMainDisplayID();
        CGVirtualDisplayDescriptor *descriptor = [[CGVirtualDisplayDescriptor alloc] init];
        descriptor.queue = dispatch_get_main_queue();
        descriptor.name = @"Pictures 2x";
        descriptor.maxPixelsWide = pointsWide * 2;
        descriptor.maxPixelsHigh = pointsHigh * 2;
        descriptor.sizeInMillimeters = CGSizeMake(330, 206);
        descriptor.vendorID = 0x4D52;
        descriptor.productID = 0x0002;
        descriptor.serialNum = 1;
        CGVirtualDisplay *display = [[CGVirtualDisplay alloc] initWithDescriptor:descriptor];
        if (!display) {
            fprintf(stderr, "hidpi_display: no virtual display\n");
            return 1;
        }
        CGVirtualDisplaySettings *settings = [[CGVirtualDisplaySettings alloc] init];
        settings.hiDPI = 1;
        settings.modes = @[[[CGVirtualDisplayMode alloc] initWithWidth:pointsWide height:pointsHigh refreshRate:60]];
        if (![display applySettings:settings]) {
            fprintf(stderr, "hidpi_display: the settings were refused\n");
            return 1;
        }
        CGDirectDisplayID virtual = display.displayID;
        [NSThread sleepForTimeInterval:2];

        // Its 2× mode, if the system listed it separately.
        NSDictionary *options = @{(__bridge NSString *)kCGDisplayShowDuplicateLowResolutionModes: @YES};
        CFArrayRef modes = CGDisplayCopyAllDisplayModes(virtual, (__bridge CFDictionaryRef)options);
        CGDisplayModeRef retina = NULL;
        for (CFIndex i = 0; modes && i < CFArrayGetCount(modes); i++) {
            CGDisplayModeRef mode = (CGDisplayModeRef)CFArrayGetValueAtIndex(modes, i);
            printf("hidpi_display: mode %zu×%zu points, %zu×%zu pixels\n", CGDisplayModeGetWidth(mode),
                   CGDisplayModeGetHeight(mode), CGDisplayModeGetPixelWidth(mode), CGDisplayModeGetPixelHeight(mode));
            if (CGDisplayModeGetPixelWidth(mode) == 2 * CGDisplayModeGetWidth(mode) && CGDisplayModeGetWidth(mode) == pointsWide) {
                retina = mode;
            }
        }

        // The virtual display becomes the main one (at the origin, with the menu bar), the real one goes to its right.
        CGDisplayConfigRef config;
        CGBeginDisplayConfiguration(&config);
        if (retina) CGConfigureDisplayWithDisplayMode(config, virtual, retina, NULL);
        CGConfigureDisplayOrigin(config, virtual, 0, 0);
        CGConfigureDisplayOrigin(config, real, (int32_t)pointsWide, 0);
        CGError result = CGCompleteDisplayConfiguration(config, kCGConfigureForSession);
        if (modes) CFRelease(modes);
        [NSThread sleepForTimeInterval:2];

        CGDisplayModeRef now = CGDisplayCopyDisplayMode(CGMainDisplayID());
        printf("hidpi_display: configured (%d); main display %u (virtual %u): %zu×%zu points, %zu×%zu pixels\n", result,
               CGMainDisplayID(), virtual, CGDisplayModeGetWidth(now), CGDisplayModeGetHeight(now),
               CGDisplayModeGetPixelWidth(now), CGDisplayModeGetPixelHeight(now));
        CGDisplayModeRelease(now);
        fflush(stdout);
        [[NSRunLoop mainRunLoop] run];   // the display lasts as long as this process
    }
    return 0;
}
