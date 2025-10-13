import 'package:flutter/material.dart';
import 'screens/splash_screen.dart';
import 'screens/create_account_screen.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';

void main() {
  runApp(const AIAnalystApp());
}

class AIAnalystApp extends StatelessWidget {
  const AIAnalystApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Analyst',
      theme: ThemeData(
        brightness: Brightness.dark,
        primaryColor: const Color(0xFF1a1a1a),
        scaffoldBackgroundColor: const Color(0xFF1a1a1a),
        primarySwatch: Colors.blue,
        visualDensity: VisualDensity.adaptivePlatformDensity,
      ),
      debugShowCheckedModeBanner: false,
      // Define the routes for the app
      initialRoute: '/',
      routes: {
        '/': (context) => const SplashScreen(),
        '/create_account': (context) => const CreateAccountScreen(),
        '/login': (context) => const LoginScreen(),
        '/home': (context) => const HomeScreen(),
      },
    );
  }
}