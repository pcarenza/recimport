package com.recimport.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import com.recimport.app.net.RtkFile
import java.io.File

object RtkFiles {
    fun writeToCache(context: Context, file: RtkFile): Uri {
        val dir = File(context.cacheDir, "rtk")
        dir.mkdirs()
        dir.listFiles()?.forEach { it.delete() }
        val safeName = file.filename.replace(Regex("[^A-Za-z0-9._-]"), "_").ifBlank { "recipe.rtk" }
        val f = File(dir, safeName)
        f.writeBytes(file.bytes)
        return FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", f)
    }

    fun shareIntent(uri: Uri): Intent {
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "application/octet-stream"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        return Intent.createChooser(send, "Send .rtk to…").apply {
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
    }

    fun viewIntent(uri: Uri): Intent =
        Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/octet-stream")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
}
