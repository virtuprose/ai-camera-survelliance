import AVFoundation

var deviceTypes: [AVCaptureDevice.DeviceType] = [.builtInWideAngleCamera]

if #available(macOS 14.0, *) {
    deviceTypes.append(.external)
} else {
    deviceTypes.append(.externalUnknown)
}

if #available(macOS 13.0, *) {
    deviceTypes.append(.continuityCamera)
}

let session = AVCaptureDevice.DiscoverySession(
    deviceTypes: deviceTypes,
    mediaType: .video,
    position: .unspecified
)

var seen = Set<String>()
var index = 0

for device in session.devices where seen.insert(device.uniqueID).inserted {
    print("\(index)\t\(device.localizedName)\t\(device.uniqueID)")
    index += 1
}
