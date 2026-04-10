import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../config.dart';

class ProfileSetupScreen extends StatefulWidget {
  const ProfileSetupScreen({super.key});
  @override
  State<ProfileSetupScreen> createState() => _ProfileSetupScreenState();
}

class _ProfileSetupScreenState extends State<ProfileSetupScreen> {
  int _step = 0;
  bool _submitting = false;
  String? _error;
  String _gender = 'Male';

  // Step 0 — essentials
  final _heightCtrl   = TextEditingController();
  final _weightCtrl   = TextEditingController();
  // Step 1 — upper body
  final _shoulderCtrl = TextEditingController();
  final _chestCtrl    = TextEditingController();
  final _bicepCtrl    = TextEditingController();
  final _neckCtrl     = TextEditingController();
  // Step 2 — lower body
  final _waistCtrl    = TextEditingController();
  final _hipCtrl      = TextEditingController();
  final _thighCtrl    = TextEditingController();
  final _calfCtrl     = TextEditingController();
  // Step 3 — body type (phenotype)
  double _muscleFactor = 50.0;   // 0-100, maps to 0.0-1.0
  double _bodyFatFactor = 50.0;  // 0-100, maps to 0.0-1.0
  // Step 4 — device setup
  final _camHeightCtrl  = TextEditingController(text: '65');
  final _camDistCtrl    = TextEditingController(text: '100');

  static const _steps = ['Essentials', 'Upper Body', 'Lower Body', 'Body Type', 'Device Setup'];

  @override
  void dispose() {
    for (final c in [_heightCtrl, _weightCtrl, _shoulderCtrl, _chestCtrl,
                     _bicepCtrl, _neckCtrl, _waistCtrl, _hipCtrl, _thighCtrl,
                     _calfCtrl, _camHeightCtrl, _camDistCtrl]) {
      c.dispose();
    }
    super.dispose();
  }

  double? _parse(TextEditingController c) => double.tryParse(c.text.trim());

  Future<void> _submit() async {
    setState(() { _submitting = true; _error = null; });
    try {
      // Submit body profile
      final profile = <String, dynamic>{};
      void add(String k, double? v) { if (v != null && v > 0) profile[k] = v; }
      add('height_cm',              _parse(_heightCtrl));
      add('weight_kg',              _parse(_weightCtrl));
      add('shoulder_width_cm',      _parse(_shoulderCtrl));
      add('chest_circumference_cm', _parse(_chestCtrl));
      add('bicep_circumference_cm', _parse(_bicepCtrl));
      add('neck_circumference_cm',  _parse(_neckCtrl));
      add('waist_circumference_cm', _parse(_waistCtrl));
      add('hip_circumference_cm',   _parse(_hipCtrl));
      add('thigh_circumference_cm', _parse(_thighCtrl));
      add('calf_circumference_cm',  _parse(_calfCtrl));
      profile['skin_tone_hex'] = 'C4956A'; // default light-brown
      profile['gender'] = _gender;
      profile['muscle_factor'] = _muscleFactor / 100.0;  // 0-100 → 0.0-1.0
      profile['weight_factor'] = _bodyFatFactor / 100.0;
      profile['gender_factor'] = _gender == 'Male' ? 1.0 : (_gender == 'Female' ? 0.0 : 0.5);

      await http.post(
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/body_profile'),
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $jwtToken'},
        body: jsonEncode(profile),
      ).timeout(const Duration(seconds: 8));

      // Submit device profile
      final camH = _parse(_camHeightCtrl) ?? 65.0;
      final camD = _parse(_camDistCtrl)   ?? 100.0;
      await http.post(
        Uri.parse('${AppConfig.serverBaseUrl}/api/customer/$customerId/devices'),
        headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer $jwtToken'},
        body: jsonEncode({
          'device_name': 'Phone',
          'role': 'front',
          'orientation': 'portrait',
          'camera_height_from_ground_cm': camH,
          'distance_to_subject_cm': camD,
        }),
      ).timeout(const Duration(seconds: 8));

      AppConfig.profileCompleted = true;
      if (mounted) {
        Navigator.pushReplacementNamed(context, '/home');
      }
    } catch (e) {
      setState(() { _error = 'Could not save profile. Tap Skip to continue.'; });
    } finally {
      setState(() { _submitting = false; });
    }
  }

  Widget _sliderField(String label, double value, String minLabel, String maxLabel, ValueChanged<double> onChanged) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label, style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 14)),
        Text('${value.round()}%', style: const TextStyle(color: Color(0xFF009688), fontSize: 16, fontWeight: FontWeight.bold)),
      ]),
      const SizedBox(height: 4),
      Row(children: [
        Text(minLabel, style: const TextStyle(color: Colors.white38, fontSize: 11)),
        Expanded(child: Slider(
          value: value, min: 0, max: 100, divisions: 20,
          activeColor: const Color(0xFF009688),
          onChanged: onChanged,
        )),
        Text(maxLabel, style: const TextStyle(color: Colors.white38, fontSize: 11)),
      ]),
    ]);
  }

  Widget _field(String label, TextEditingController ctrl, String unit, {String? hint}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(children: [
        Expanded(
          child: TextField(
            controller: ctrl,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              labelText: label,
              hintText: hint,
              labelStyle: const TextStyle(color: Color(0xFF94A3B8)),
              hintStyle: const TextStyle(color: Color(0xFF475569), fontSize: 12),
              enabledBorder: const OutlineInputBorder(borderSide: BorderSide(color: Color(0xFF334155))),
              focusedBorder: const OutlineInputBorder(borderSide: BorderSide(color: Color(0xFF009688))),
              filled: true, fillColor: const Color(0xFF121212),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(width: 36, child: Text(unit, style: const TextStyle(color: Color(0xFF94A3B8)))),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        title: Text('Setup — ${_steps[_step]}'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pushReplacementNamed(context, '/home'),
            child: const Text('Skip', style: TextStyle(color: Color(0xFF94A3B8))),
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(children: [
            // Step indicator
            Row(mainAxisAlignment: MainAxisAlignment.center, children: List.generate(
              _steps.length, (i) => Container(
                margin: const EdgeInsets.symmetric(horizontal: 4),
                width: 10, height: 10,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i <= _step ? const Color(0xFF009688) : const Color(0xFF334155),
                ),
              ),
            )),
            const SizedBox(height: 20),
            Expanded(
              child: SingleChildScrollView(child: Column(children: [
                if (_step == 0) ...[
                  const Text('Enter your basic measurements.\nHeight and weight are required.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 12),
                  _field('Height *', _heightCtrl, 'cm'),
                  _field('Weight *', _weightCtrl, 'kg'),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    value: _gender,
                    dropdownColor: AppTheme.cardBg,
                    decoration: const InputDecoration(
                      labelText: 'Gender',
                      prefixIcon: Icon(Icons.people, size: 18),
                    ),
                    items: ['Male', 'Female', 'Other']
                        .map((g) => DropdownMenuItem(value: g, child: Text(g)))
                        .toList(),
                    onChanged: (v) => setState(() => _gender = v!),
                  ),
                ],
                if (_step == 1) ...[
                  const Text('Upper body — all optional but improves 3D accuracy.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 12),
                  _field('Shoulder width', _shoulderCtrl, 'cm', hint: 'Edge to edge'),
                  _field('Chest circumference', _chestCtrl, 'cm', hint: 'At nipple height'),
                  _field('Bicep circumference', _bicepCtrl, 'cm', hint: 'Widest part, arm at side'),
                  _field('Neck circumference', _neckCtrl, 'cm'),
                ],
                if (_step == 2) ...[
                  const Text('Lower body — all optional.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 12),
                  _field('Waist', _waistCtrl, 'cm', hint: 'Below belly button'),
                  _field('Hip / Buttock', _hipCtrl, 'cm'),
                  _field('Upper thigh', _thighCtrl, 'cm'),
                  _field('Calf', _calfCtrl, 'cm'),
                ],
                if (_step == 3) ...[
                  const Text('Describe your body type.\nThis fine-tunes your 3D model.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 20),
                  _sliderField('Muscle Definition', _muscleFactor, 'Low', 'High',
                      (v) => setState(() => _muscleFactor = v)),
                  const SizedBox(height: 16),
                  _sliderField('Body Fat', _bodyFatFactor, 'Lean', 'Heavy',
                      (v) => setState(() => _bodyFatFactor = v)),
                ],
                if (_step == 4) ...[
                  const Text('Tell us how your devices are set up.\nThis calibrates the camera distance.',
                      textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
                  const SizedBox(height: 12),
                  _field('Camera height from floor', _camHeightCtrl, 'cm',
                      hint: 'Chair height + device position (e.g. 65)'),
                  _field('Distance to subject', _camDistCtrl, 'cm',
                      hint: '100 = 1 metre, 50 = half metre'),
                ],
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(_error!, style: const TextStyle(color: Color(0xFFFF5252), fontSize: 12)),
                  ),
              ])),
            ),
            Row(children: [
              if (_step > 0)
                Expanded(child: OutlinedButton(
                  onPressed: () => setState(() => _step--),
                  child: const Text('Back'),
                )),
              if (_step > 0) const SizedBox(width: 12),
              Expanded(child: FilledButton(
                onPressed: _submitting ? null
                    : (_step < _steps.length - 1)
                        ? () => setState(() => _step++)
                        : _submit,
                child: _submitting
                    ? const SizedBox(width: 20, height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black))
                    : Text(_step < _steps.length - 1 ? 'Next' : 'Save & Start'),
              )),
            ]),
          ]),
        ),
      ),
    );
  }
}
