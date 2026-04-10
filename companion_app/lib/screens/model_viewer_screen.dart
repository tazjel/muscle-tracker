import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../config.dart';

class ModelViewerScreen extends StatefulWidget {
  final int meshId;
  final String? title;
  const ModelViewerScreen({super.key, required this.meshId, this.title});

  @override
  State<ModelViewerScreen> createState() => _ModelViewerScreenState();
}

class _ModelViewerScreenState extends State<ModelViewerScreen> {
  late final WebViewController _controller;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageFinished: (_) => setState(() => _loading = false),
      ))
      ..loadRequest(Uri.parse(
        '${AppConfig.serverBaseUrl}/static/viewer3d/index.html'
        '?model=/api/mesh/${widget.meshId}.glb'
        '&customer=${customerId ?? "1"}'
      ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        title: Text(widget.title ?? '3D Body Model',
            style: const TextStyle(fontSize: 16)),
        backgroundColor: const Color(0xFF161B22),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Stack(
        children: [
          WebViewWidget(controller: _controller),
          if (_loading)
            const Center(child: CircularProgressIndicator(
              color: AppTheme.primaryTeal,
            )),
        ],
      ),
    );
  }
}
