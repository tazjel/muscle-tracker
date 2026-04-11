import 'dart:io';
import 'dart:math';
import 'dart:typed_data';
import 'package:path_provider/path_provider.dart';

/// Secure file deletion — overwrites content with random bytes before removing.
/// Prevents forensic recovery of sensitive body images.
class SecureDelete {
  static final _rng = Random.secure();

  /// Overwrite file with random bytes, then delete it.
  static Future<void> file(File f) async {
    try {
      if (!await f.exists()) return;
      final length = await f.length();
      if (length > 0) {
        // Overwrite with random bytes
        final noise = Uint8List(length);
        for (var i = 0; i < length; i++) {
          noise[i] = _rng.nextInt(256);
        }
        await f.writeAsBytes(noise, flush: true);
        // Second pass: zeros
        await f.writeAsBytes(Uint8List(length), flush: true);
      }
      await f.delete();
    } catch (_) {
      // Best-effort: try plain delete if overwrite fails
      try { await f.delete(); } catch (_) {}
    }
  }

  /// Securely delete a file by path string.
  static Future<void> path(String filePath) async {
    await file(File(filePath));
  }

  /// Securely delete all files in a directory, then remove the directory.
  static Future<void> directory(Directory dir) async {
    try {
      if (!await dir.exists()) return;
      await for (final entity in dir.list(recursive: true)) {
        if (entity is File) {
          await file(entity);
        }
      }
      await dir.delete(recursive: true);
    } catch (_) {
      try { await dir.delete(recursive: true); } catch (_) {}
    }
  }

  /// Wipe all GTD3D image data from the device.
  /// Call on app startup and when user requests data purge.
  static Future<void> purgeAll() async {
    try {
      // 1. Persistent scans directory
      final docsDir = await getApplicationDocumentsDirectory();
      final scansDir = Directory('${docsDir.path}/scans');
      await directory(scansDir);

      // 2. Any report images in documents
      await for (final entity in docsDir.list()) {
        if (entity is File) {
          final name = entity.path.split('/').last.split('\\').last;
          if (name.startsWith('report_') || name.startsWith('latest_scan_')) {
            await file(entity);
          }
        }
      }

      // 3. Temp directory: wipe all GTD3D temp files
      final tmpDir = await getTemporaryDirectory();

      // muscle_dual captures
      final dualDir = Directory('${tmpDir.path}/muscle_dual');
      await directory(dualDir);

      // Profile session captures
      await for (final entity in tmpDir.list()) {
        if (entity is Directory) {
          final name = entity.path.split('/').last.split('\\').last;
          if (name.startsWith('profile_session_')) {
            await directory(entity);
          }
        }
        if (entity is File) {
          final name = entity.path.split('/').last.split('\\').last;
          if (name.startsWith('live_') ||
              name.startsWith('r_') ||
              name.startsWith('session_report_') ||
              name.endsWith('.jpg') ||
              name.endsWith('.png')) {
            await file(entity);
          }
        }
      }

      // 4. Camera cache (XFile temp files)
      final cacheDir = Directory('${tmpDir.path}');
      await for (final entity in cacheDir.list()) {
        if (entity is File) {
          final name = entity.path.split('/').last.split('\\').last;
          if (name.startsWith('CAP') || name.startsWith('IMG') || name.startsWith('camera_')) {
            await file(entity);
          }
        }
      }
    } catch (_) {}
  }

  /// Delete a single XFile after it has been used (uploaded, processed, etc.)
  static Future<void> xfile(dynamic xf) async {
    try {
      if (xf != null && xf.path != null) {
        await path(xf.path);
      }
    } catch (_) {}
  }
}
