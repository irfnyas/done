import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';

void main() {
  runApp(const DoneApp());
}

class DoneApp extends StatefulWidget {
  const DoneApp({super.key});

  @override
  State<DoneApp> createState() => _DoneAppState();
}

class _DoneAppState extends State<DoneApp> {
  ThemeMode _themeMode = ThemeMode.system;

  void _toggleTheme() {
    setState(() {
      _themeMode = _themeMode == ThemeMode.dark
          ? ThemeMode.light
          : ThemeMode.dark;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DONE',
      debugShowCheckedModeBanner: false,
      themeMode: _themeMode,
      theme: ThemeData(
        brightness: Brightness.light,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFA0BAD4),
          primary: const Color(0xFFA0BAD4),
          brightness: Brightness.light,
        ),
        appBarTheme: AppBarTheme(centerTitle: true),
      ),
      darkTheme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFA0BAD4),
          primary: const Color(0xFF7799C0),
          brightness: Brightness.dark,
        ),
        appBarTheme: AppBarTheme(centerTitle: true),
      ),
      home: ConnectionScreen(onThemeToggle: _toggleTheme),
    );
  }
}

class ConnectionScreen extends StatefulWidget {
  final VoidCallback onThemeToggle;
  const ConnectionScreen({super.key, required this.onThemeToggle});

  @override
  State<ConnectionScreen> createState() => _ConnectionScreenState();
}

class _ConnectionScreenState extends State<ConnectionScreen> {
  final TextEditingController _ipController = TextEditingController();
  final TextEditingController _portController = TextEditingController(
    text: "5005",
  );
  bool _isSearching = false;

  void _connect(String ip, int port) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => RemoteControlScreen(
          serverIp: ip,
          serverPort: port,
          onThemeToggle: widget.onThemeToggle,
        ),
      ),
    );
  }

  Future<void> _autoConnect() async {
    setState(() => _isSearching = true);
    try {
      final RawDatagramSocket socket = await RawDatagramSocket.bind(
        InternetAddress.anyIPv4,
        0,
      );
      socket.broadcastEnabled = true;
      final pingData = jsonEncode({'type': 'ping'});
      for (int i = 0; i < 3; i++) {
        socket.send(
          utf8.encode(pingData),
          InternetAddress("255.255.255.255"),
          5005,
        );
        await Future.delayed(const Duration(milliseconds: 500));
      }
      socket.listen((RawSocketEvent event) {
        if (event == RawSocketEvent.read) {
          final Datagram? dg = socket.receive();
          if (dg != null) {
            final response = jsonDecode(utf8.decode(dg.data));
            if (response['type'] == 'pong') {
              socket.close();
              if (mounted) _connect(dg.address.address, 5005);
            }
          }
        }
      });
      await Future.delayed(const Duration(seconds: 3));
      socket.close();
    } catch (e) {
      debugPrint("Discovery Error: $e");
    }
    if (mounted) setState(() => _isSearching = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        actions: [
          IconButton(
            icon: Icon(
              Theme.of(context).brightness == Brightness.dark
                  ? Icons.light_mode
                  : Icons.dark_mode,
            ),
            onPressed: widget.onThemeToggle,
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Image.asset(
                Theme.of(context).brightness == Brightness.dark
                    ? 'assets/icon-hz-dark.png'
                    : 'assets/icon-hz.png',
                height: 80,
              ),
              const SizedBox(height: 24),
              Text(
                'Context-Aware Productivity Assistant',
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.grey.withOpacity(0.8),
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 48),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _isSearching ? null : _autoConnect,
                  icon: _isSearching
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.search),
                  label: Text(_isSearching ? 'Searching...' : 'Auto Connect'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.primary,
                    foregroundColor: Colors.black,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const Text('OR', style: TextStyle(color: Colors.grey)),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: _showManualConnectDialog,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Theme.of(context).colorScheme.onSurface,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  child: const Text('Connect Manually'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showManualConnectDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Manual Connection'),
        content: TextField(
          controller: _ipController,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'Server IP',
            hintText: '10.0.2.X',
            border: OutlineInputBorder(),
          ),
          keyboardType: TextInputType.number,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (_ipController.text.isNotEmpty) {
                Navigator.pop(context); // Close dialog
                _connect(_ipController.text, int.parse(_portController.text));
              }
            },
            child: const Text('Connect'),
          ),
        ],
      ),
    );
  }
}

class RemoteControlScreen extends StatefulWidget {
  final String serverIp;
  final int serverPort;
  final VoidCallback onThemeToggle;

  const RemoteControlScreen({
    super.key,
    required this.serverIp,
    required this.serverPort,
    required this.onThemeToggle,
  });

  @override
  State<RemoteControlScreen> createState() => _RemoteControlScreenState();
}

class _RemoteControlScreenState extends State<RemoteControlScreen> {
  late RawDatagramSocket _socket;
  String appName = 'Waiting...';
  String contextInfo = '';
  List<dynamic> actions = [];
  bool ollamaActive = false;

  DateTime _lastHeartbeat = DateTime.now();
  Timer? _heartbeatTimer;

  @override
  void initState() {
    super.initState();
    _initSocket();
    _startHeartbeatTimer();
  }

  void _startHeartbeatTimer() {
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (DateTime.now().difference(_lastHeartbeat).inSeconds > 5) {
        _showConnectionLostDialog();
        timer.cancel();
      }
    });
  }

  void _showConnectionLostDialog() {
    if (!mounted) return;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        title: const Text('Connection Lost'),
        content: const Text('The desktop app is not responding.'),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(context).pop(); // Close dialog
              Navigator.of(context).pop(); // Back to menu
            },
            child: const Text('Back to Menu'),
          ),
        ],
      ),
    );
  }

  Future<void> _initSocket() async {
    _socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    _socket.listen((RawSocketEvent event) {
      if (event == RawSocketEvent.read) {
        final Datagram? dg = _socket.receive();
        if (dg != null) {
          setState(() {
            final data = jsonDecode(utf8.decode(dg.data));
            if (data['type'] == 'state_update') {
              appName = data['display_name'] ?? data['app_name'] ?? 'Unknown';
              contextInfo = data['inferred_context'] ?? '';
              actions = data['actions'] ?? [];
              ollamaActive = data['ollama_active'] ?? false;
            }
            _lastHeartbeat = DateTime.now();
          });
        }
      }
    });
    _sendCommand('ping');
    Timer.periodic(const Duration(seconds: 3), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      _sendCommand('ping');
    });
  }

  void _sendCommand(String cmd) {
    final data = jsonEncode({'type': 'command', 'command': cmd});
    _socket.send(
      utf8.encode(data),
      InternetAddress(widget.serverIp),
      widget.serverPort,
    );
  }

  @override
  void dispose() {
    _heartbeatTimer?.cancel();
    _socket.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          spacing: 2,
          children: [
            Text(appName, textAlign: TextAlign.center),
            Visibility(
              visible: contextInfo.isNotEmpty,
              child: Text(
                contextInfo,
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: Colors.grey),
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: () {
              _sendCommand('refresh');
            },
          ),
          IconButton(
            icon: Icon(
              Theme.of(context).brightness == Brightness.dark
                  ? Icons.light_mode
                  : Icons.dark_mode,
            ),
            onPressed: widget.onThemeToggle,
          ),
        ],
      ),
      bottomNavigationBar:
          (appName == 'Waiting...' || contextInfo.startsWith('Loading...'))
          ? LinearProgressIndicator(
              backgroundColor: Colors.transparent,
              minHeight: 2,
            )
          : null,
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: 16,
          children: [
            ...() {
              final filteredActions = actions
                  .where((act) => (act['shortcut'] ?? 'None') != 'None')
                  .toList();
              return filteredActions.mapIndexed((index, act) {
                final String shortcut = act['shortcut'];

                return Expanded(
                  child: OutlinedButton(
                    onPressed: () => _sendCommand('key:$shortcut'),
                    style: OutlinedButton.styleFrom(
                      backgroundColor: index == filteredActions.length - 1
                          ? Theme.of(context).colorScheme.primary
                          : null,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                    child: Center(
                      child: Text(
                        act['action_name'],
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                    ),
                  ),
                );
              });
            }(),
          ],
        ),
      ),
    );
  }
}
