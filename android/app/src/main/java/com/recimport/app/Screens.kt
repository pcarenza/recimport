package com.recimport.app

import android.content.ActivityNotFoundException
import android.content.Context
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.recimport.app.net.RtkFile

@Composable
fun App(vm: MainViewModel, state: UiState, sharedText: String?) {
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    var link by remember { mutableStateOf(sharedText ?: "") }
    var lastText by remember { mutableStateOf(sharedText ?: "") }
    LaunchedEffect(sharedText) {
        if (!sharedText.isNullOrBlank()) {
            link = sharedText
            lastText = sharedText
        }
    }
    val initial = remember { vm.loadSettings() }
    var showSettings by remember { mutableStateOf(initial.baseUrl.isBlank() || initial.token.isBlank()) }
    var baseUrl by remember { mutableStateOf(initial.baseUrl) }
    var token by remember { mutableStateOf(initial.token) }
    var geminiKey by remember { mutableStateOf(initial.geminiKey) }
    val working = state is UiState.Working

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Recipe Importer", style = MaterialTheme.typography.headlineMedium)

        OutlinedTextField(
            value = link,
            onValueChange = { link = it },
            label = { Text("Paste a YouTube, Facebook or Instagram reel link") },
            modifier = Modifier.fillMaxWidth()
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = {
                val t = clipboard.getText()?.text
                if (!t.isNullOrBlank()) link = t
            }) { Text("Paste") }
            Button(
                enabled = link.isNotBlank() && !working,
                onClick = {
                    lastText = link
                    vm.start(link)
                }
            ) { Text("Extract recipe") }
        }

        TextButton(onClick = { showSettings = !showSettings }) {
            Text(if (showSettings) "Hide settings" else "Settings")
        }
        if (showSettings) {
            OutlinedTextField(
                value = baseUrl,
                onValueChange = { baseUrl = it },
                label = { Text("Backend URL (https://…onrender.com)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                label = { Text("App token") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = geminiKey,
                onValueChange = { geminiKey = it },
                label = { Text("Gemini key (optional)") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth()
            )
            Button(onClick = {
                vm.saveSettings(baseUrl, token, geminiKey)
                showSettings = false
                Toast.makeText(context, "Settings saved", Toast.LENGTH_SHORT).show()
            }) { Text("Save") }
        }

        HorizontalDivider()

        when (state) {
            is UiState.Idle -> {}
            is UiState.Working -> Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                CircularProgressIndicator()
                Text(state.message, modifier = Modifier.padding(top = 12.dp))
            }
            is UiState.Failed -> {
                Text(state.message, color = MaterialTheme.colorScheme.error)
                Button(
                    enabled = lastText.isNotBlank(),
                    onClick = { vm.start(lastText) }
                ) { Text("Retry") }
            }
            is UiState.Done -> DoneView(state)
        }
    }
}

@Composable
private fun DoneView(state: UiState.Done) {
    val context = LocalContext.current
    val file: RtkFile = state.file
    val saveLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/octet-stream")
    ) { uri ->
        if (uri != null) {
            val ok = try {
                context.contentResolver.openOutputStream(uri)?.use { it.write(file.bytes) } != null
            } catch (e: Exception) {
                false
            }
            Toast.makeText(context, if (ok) "Saved" else "Could not save file", Toast.LENGTH_SHORT).show()
        }
    }

    val r = state.recipe
    Text(state.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
    if (r != null) {
        if (r.description.isNotBlank()) Text(r.description)
        val info = listOfNotNull(
            r.preparationTime.takeIf { it.isNotBlank() }?.let { "Prep: $it" },
            r.cookingTime.takeIf { it.isNotBlank() }?.let { "Cook: $it" },
            r.totalTime.takeIf { it > 0 }?.let { "Total: $it min" },
            r.quantity.takeIf { it.isNotBlank() }?.let { "Serves: $it" }
        ).joinToString("  •  ")
        if (info.isNotBlank()) Text(info, style = MaterialTheme.typography.bodyMedium)

        Text("Ingredients", style = MaterialTheme.typography.titleMedium)
        r.ingredients.forEach { Text("•  $it") }
        Text("Instructions", style = MaterialTheme.typography.titleMedium)
        r.instructions.forEachIndexed { i, s -> Text("${i + 1}. $s") }
    }

    Button(onClick = {
        launchSafely(context) {
            val uri = RtkFiles.writeToCache(context, file)
            try {
                context.startActivity(RtkFiles.viewIntent(uri))
            } catch (e: ActivityNotFoundException) {
                context.startActivity(RtkFiles.shareIntent(uri))
            }
        }
    }, modifier = Modifier.fillMaxWidth()) { Text("Send to My Recipe Box") }

    OutlinedButton(onClick = {
        launchSafely(context) {
            context.startActivity(RtkFiles.shareIntent(RtkFiles.writeToCache(context, file)))
        }
    }, modifier = Modifier.fillMaxWidth()) { Text("Share / save file") }

    OutlinedButton(
        onClick = { saveLauncher.launch(file.filename) },
        modifier = Modifier.fillMaxWidth()
    ) { Text("Save to device") }
}

private fun launchSafely(context: Context, block: () -> Unit) {
    try {
        block()
    } catch (e: ActivityNotFoundException) {
        Toast.makeText(context, "No app available to handle the file", Toast.LENGTH_LONG).show()
    } catch (e: Exception) {
        Toast.makeText(context, "Failed: ${e.message}", Toast.LENGTH_LONG).show()
    }
}
