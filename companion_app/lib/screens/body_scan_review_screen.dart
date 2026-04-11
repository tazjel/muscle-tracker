import 'dart:convert';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:webview_flutter/webview_flutter.dart';
import '../services/secure_delete.dart';

class BodyScanReviewScreen extends StatefulWidget {
  final int customerId;
  final String sessionId;
  final String serverBaseUrl;
  final String? token;

  const BodyScanReviewScreen({
    super.key,
    required this.customerId,
    required this.sessionId,
    required this.serverBaseUrl,
    this.token,
  });

  @override
  State<BodyScanReviewScreen> createState() => _BodyScanReviewScreenState();
}

class _BodyScanReviewScreenState extends State<BodyScanReviewScreen> {
  List<Map<String, dynamic>> _tasks = [];
  bool _loading = true;
  bool _processing = false;
  String? _error;
  String? _viewerUrl;
  String _statusMessage = '';

  // Track per-region confirmation state
  final Map<String, bool?> _confirmations = {};

  @override
  void initState() {
    super.initState();
    _fetchTasks();
  }

  Map<String, String> get _authHeaders {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (widget.token != null) headers['Authorization'] = 'Bearer ${widget.token}';
    return headers;
  }

  Future<void> _fetchTasks() async {
    setState(() { _loading = true; _error = null; });
    try {
      final uri = Uri.parse(
        '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/tasks');
      final resp = await http.get(uri, headers: _authHeaders);
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        final taskList = (data['task_list'] as List? ?? [])
            .map((t) => Map<String, dynamic>.from(t))
            .toList();
        setState(() {
          _tasks = taskList;
          _loading = false;
          // Initialize confirmation state
          for (final task in taskList) {
            final region = task['region'] as String? ?? '';
            if (!_confirmations.containsKey(region)) {
              _confirmations[region] = null; // pending
            }
          }
        });
      } else {
        setState(() { _error = 'Server error: ${resp.statusCode}'; _loading = false; });
      }
    } catch (e) {
      setState(() { _error = 'Connection error: $e'; _loading = false; });
    }
  }

  Future<void> _confirmRegion(String region, bool confirmed) async {
    setState(() { _confirmations[region] = confirmed; });

    try {
      final uri = Uri.parse(
        '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/confirm');
      final resp = await http.post(uri,
        headers: _authHeaders,
        body: jsonEncode({
          'confirmations': [{'region': region, 'confirmed': confirmed}]
        }),
      );
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        if (data['task_list'] != null) {
          setState(() {
            _tasks = (data['task_list'] as List)
                .map((t) => Map<String, dynamic>.from(t))
                .toList();
          });
        }
      }
    } catch (e) {
      debugPrint('Confirm error: $e');
    }
  }

  Future<void> _startRecapture(String region) async {
    final result = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => RegionRecaptureScreen(
        region: region,
        customerId: widget.customerId,
        sessionId: widget.sessionId,
        serverBaseUrl: widget.serverBaseUrl,
        token: widget.token,
      ),
    ));

    if (result == true) {
      await _fetchTasks();
    }
  }

  Future<void> _finalizeAll() async {
    setState(() { _processing = true; _statusMessage = 'Processing final model...'; });
    try {
      final uri = Uri.parse(
        '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/finalize');
      final resp = await http.post(uri, headers: _authHeaders);
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        setState(() {
          _processing = false;
          _viewerUrl = data['viewer_url'];
          _statusMessage = 'Model complete!';
        });
      } else {
        setState(() {
          _processing = false;
          _statusMessage = 'Processing failed: ${resp.statusCode}';
        });
      }
    } catch (e) {
      setState(() { _processing = false; _statusMessage = 'Error: $e'; });
    }
  }

  void _openInBrowser() {
    if (_viewerUrl != null) {
      Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => Scaffold(
          appBar: AppBar(
            title: const Text('3D Body Viewer'),
            backgroundColor: Colors.deepPurple,
          ),
          body: WebViewWidget(
            controller: WebViewController()
              ..setJavaScriptMode(JavaScriptMode.unrestricted)
              ..loadRequest(Uri.parse('${widget.serverBaseUrl}$_viewerUrl')),
          ),
        ),
      ));
    }
  }

  Color _gradeColor(String grade) {
    switch (grade) {
      case 'excellent': return Colors.green;
      case 'good': return Colors.lightGreen;
      case 'fair': return Colors.orange;
      default: return Colors.red;
    }
  }

  IconData _gradeIcon(String grade) {
    switch (grade) {
      case 'excellent': return Icons.check_circle;
      case 'good': return Icons.check_circle_outline;
      case 'fair': return Icons.warning_amber;
      default: return Icons.error_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Body Scan Review'),
        backgroundColor: Colors.deepPurple,
        foregroundColor: Colors.white,
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator())
        : _error != null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(_error!, style: const TextStyle(color: Colors.red, fontSize: 16)),
                  const SizedBox(height: 16),
                  ElevatedButton(onPressed: _fetchTasks, child: const Text('RETRY')),
                ],
              ),
            )
          : Column(
              children: [
                // Status bar
                if (_statusMessage.isNotEmpty)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    color: _viewerUrl != null ? Colors.green.shade700 : Colors.deepPurple.shade700,
                    child: Text(_statusMessage,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 16)),
                  ),

                // Task list
                Expanded(
                  child: ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _tasks.length,
                    itemBuilder: (ctx, i) {
                      final task = _tasks[i];
                      final region = task['region'] as String? ?? '';
                      final grade = task['grade'] as String? ?? 'missing';
                      final message = task['message'] as String? ?? '';
                      final action = task['action'] as String? ?? 'confirm';
                      final thumbnailIdx = task['thumbnail_idx'] ?? 0;
                      final confirmed = _confirmations[region];

                      return Card(
                        margin: const EdgeInsets.only(bottom: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                          side: BorderSide(
                            color: confirmed == true ? Colors.green
                                : confirmed == false ? Colors.red
                                : Colors.grey.shade300,
                            width: confirmed != null ? 2 : 1,
                          ),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Region header with grade
                              Row(
                                children: [
                                  Icon(_gradeIcon(grade), color: _gradeColor(grade), size: 28),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      region.replaceAll('_', ' ').toUpperCase(),
                                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                                    ),
                                  ),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: _gradeColor(grade).withOpacity(0.15),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: Text(grade.toUpperCase(),
                                      style: TextStyle(color: _gradeColor(grade), fontWeight: FontWeight.bold)),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 8),

                              // Thumbnail
                              ClipRRect(
                                borderRadius: BorderRadius.circular(8),
                                child: Image.network(
                                  '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/thumbnail/$thumbnailIdx',
                                  headers: widget.token != null ? {'Authorization': 'Bearer ${widget.token}'} : null,
                                  height: 120,
                                  width: double.infinity,
                                  fit: BoxFit.cover,
                                  errorBuilder: (_, __, ___) => Container(
                                    height: 120,
                                    color: Colors.grey.shade200,
                                    child: const Center(child: Icon(Icons.image_not_supported, size: 40)),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 8),

                              // Message
                              if (message.isNotEmpty)
                                Text(message, style: TextStyle(color: Colors.grey.shade600)),
                              const SizedBox(height: 12),

                              // Action buttons
                              Row(
                                mainAxisAlignment: MainAxisAlignment.end,
                                children: [
                                  if (action == 're-capture' || grade == 'fair' || grade == 'missing')
                                    OutlinedButton.icon(
                                      onPressed: () => _startRecapture(region),
                                      icon: const Icon(Icons.camera_alt, size: 18),
                                      label: const Text('RE-CAPTURE'),
                                      style: OutlinedButton.styleFrom(foregroundColor: Colors.orange),
                                    ),
                                  const SizedBox(width: 8),
                                  if (confirmed != false)
                                    OutlinedButton.icon(
                                      onPressed: () => _confirmRegion(region, false),
                                      icon: const Icon(Icons.close, size: 18),
                                      label: const Text('REJECT'),
                                      style: OutlinedButton.styleFrom(foregroundColor: Colors.red),
                                    ),
                                  const SizedBox(width: 8),
                                  if (confirmed != true)
                                    ElevatedButton.icon(
                                      onPressed: () => _confirmRegion(region, true),
                                      icon: const Icon(Icons.check, size: 18),
                                      label: const Text('CONFIRM'),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.green,
                                        foregroundColor: Colors.white,
                                      ),
                                    ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),

      // Bottom bar
      bottomNavigationBar: Padding(
        padding: const EdgeInsets.all(16),
        child: _processing
          ? const Center(child: CircularProgressIndicator())
          : _viewerUrl != null
            ? ElevatedButton.icon(
                onPressed: _openInBrowser,
                icon: const Icon(Icons.view_in_ar, size: 24),
                label: const Text('VIEW IN BROWSER', style: TextStyle(fontSize: 18)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.deepPurple,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              )
            : ElevatedButton.icon(
                onPressed: _finalizeAll,
                icon: const Icon(Icons.check_circle, size: 24),
                label: const Text('CONFIRM ALL & BUILD', style: TextStyle(fontSize: 18)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.deepPurple,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              ),
      ),
    );
  }
}

// ── Region Re-capture Screen ──────────────────────────────────────────────────

class RegionRecaptureScreen extends StatefulWidget {
  final String region;
  final int customerId;
  final String sessionId;
  final String serverBaseUrl;
  final String? token;

  const RegionRecaptureScreen({
    super.key,
    required this.region,
    required this.customerId,
    required this.sessionId,
    required this.serverBaseUrl,
    this.token,
  });

  @override
  State<RegionRecaptureScreen> createState() => _RegionRecaptureScreenState();
}

class _RegionRecaptureScreenState extends State<RegionRecaptureScreen> {
  CameraController? _camera;
  bool _capturing = false;
  int _framesCaptured = 0;
  final int _totalFrames = 10;
  final List<String> _capturedPaths = [];
  String _instruction = '';
  bool _uploading = false;

  @override
  void initState() {
    super.initState();
    _initCamera();
  }

  Future<void> _initCamera() async {
    final cameras = await availableCameras();
    final back = cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );
    _camera = CameraController(back, ResolutionPreset.max, enableAudio: false);
    await _camera!.initialize();
    if (mounted) setState(() {});
  }

  Future<void> _startCapture() async {
    if (_capturing || _camera == null) return;
    setState(() {
      _capturing = true;
      _framesCaptured = 0;
      _capturedPaths.clear();
      _instruction = 'Point camera at your ${widget.region.replaceAll("_", " ").toUpperCase()}\nROTATE SLOWLY';
    });

    for (int i = 0; i < _totalFrames; i++) {
      if (!mounted || !_capturing) return;
      try {
        final img = await _camera!.takePicture();
        _capturedPaths.add(img.path);
        setState(() {
          _framesCaptured = i + 1;
          _instruction = '${widget.region.replaceAll("_", " ").toUpperCase()}\nFrame ${i + 1}/$_totalFrames';
        });
      } catch (e) {
        debugPrint('Recapture frame error: $e');
      }
      await Future.delayed(const Duration(seconds: 2));
    }

    setState(() { _instruction = 'Uploading...'; _uploading = true; });
    await _uploadRecapture();
  }

  Future<void> _uploadRecapture() async {
    try {
      final uri = Uri.parse(
        '${widget.serverBaseUrl}/api/customer/${widget.customerId}/body_scan/${widget.sessionId}/re_capture');
      final request = http.MultipartRequest('POST', uri);
      if (widget.token != null) {
        request.headers['Authorization'] = 'Bearer ${widget.token}';
      }
      request.fields['region'] = widget.region;

      for (int i = 0; i < _capturedPaths.length; i++) {
        request.files.add(await http.MultipartFile.fromPath(
          'frame_${i.toString().padLeft(3, '0')}',
          _capturedPaths[i],
          filename: 'frame_${i.toString().padLeft(3, '0')}.jpg',
        ));
      }

      final resp = await request.send();
      if (resp.statusCode == 200) {
        // Privacy: securely delete all captured frames after successful upload
        for (final p in _capturedPaths) {
          await SecureDelete.path(p);
        }
        _capturedPaths.clear();
        if (mounted) Navigator.of(context).pop(true);
      } else {
        for (final p in _capturedPaths) {
          await SecureDelete.path(p);
        }
        _capturedPaths.clear();
        setState(() { _instruction = 'Upload failed'; _uploading = false; _capturing = false; });
      }
    } catch (e) {
      for (final p in _capturedPaths) {
        await SecureDelete.path(p);
      }
      _capturedPaths.clear();
      setState(() { _instruction = 'Error: $e'; _uploading = false; _capturing = false; });
    }
  }

  @override
  void dispose() {
    _camera?.dispose();
    // Privacy: delete any unsent recapture frames
    for (final p in _capturedPaths) {
      SecureDelete.path(p);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Re-capture: ${widget.region.replaceAll("_", " ")}'),
        backgroundColor: Colors.orange,
        foregroundColor: Colors.white,
      ),
      body: Stack(
        children: [
          // Camera preview
          if (_camera != null && _camera!.value.isInitialized)
            SizedBox.expand(child: CameraPreview(_camera!))
          else
            const Center(child: CircularProgressIndicator()),

          // Overlay
          if (_capturing)
            Positioned.fill(
              child: Container(
                color: Colors.black45,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(_instruction,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 16),
                    LinearProgressIndicator(
                      value: _framesCaptured / _totalFrames,
                      backgroundColor: Colors.white24,
                      valueColor: const AlwaysStoppedAnimation(Colors.orange),
                    ),
                    const SizedBox(height: 8),
                    Text('$_framesCaptured / $_totalFrames frames',
                      style: const TextStyle(color: Colors.white70, fontSize: 16)),
                  ],
                ),
              ),
            ),

          // Start button
          if (!_capturing && !_uploading)
            Positioned(
              bottom: 32, left: 32, right: 32,
              child: ElevatedButton.icon(
                onPressed: _startCapture,
                icon: const Icon(Icons.camera_alt, size: 28),
                label: Text(
                  'START RE-CAPTURE: ${widget.region.replaceAll("_", " ").toUpperCase()}',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.orange,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
