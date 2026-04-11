import 'package:flutter/material.dart';

class ConnectionBanner extends StatelessWidget {
  final ValueNotifier<bool> isOnline;

  const ConnectionBanner({super.key, required this.isOnline});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: isOnline,
      builder: (context, online, _) {
        if (online) return const SizedBox.shrink();
        return Container(
          width: double.infinity,
          color: Colors.red[700],
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
          child: const Row(
            children: [
              Icon(Icons.wifi_off, color: Colors.white, size: 16),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Offline — requests will be queued',
                  style: TextStyle(color: Colors.white, fontSize: 13),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
