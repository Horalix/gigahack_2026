use crate::app_error::AppError;
use serde::Serialize;
use std::{
    fs,
    io::Write,
    path::Path,
    sync::atomic::{AtomicU64, Ordering},
};

pub fn write_json(path: &Path, value: &impl Serialize) -> Result<(), AppError> {
    let bytes = serde_json::to_vec(value).map_err(|error| AppError::Io(error.to_string()))?;
    write_bytes(path, &bytes)
}

pub fn open_ephemeral(path: &Path) -> std::io::Result<fs::File> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut options = fs::OpenOptions::new();
    options.create(true).truncate(true).read(true).write(true);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::fs::OpenOptionsExt;
        // FILE_FLAG_DELETE_ON_CLOSE: the OS also closes this handle on process termination.
        options.custom_flags(0x0400_0000);
    }
    options.open(path)
}

pub fn write_bytes(path: &Path, bytes: &[u8]) -> Result<(), AppError> {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let temporary = path.with_extension(format!(
        "{}-{}.tmp",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    let result = (|| {
        let mut file = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temporary)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(temporary);
    }
    result.map_err(Into::into)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn atomically_replaces_existing_settings_without_a_backup() {
        let dir = std::env::temp_dir().join(format!("feelsay-atomic-{}", std::process::id()));
        let path = dir.join("settings.json");
        write_json(&path, &vec![1, 2, 3]).unwrap();
        write_json(&path, &vec![4]).unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "[4]");
        assert_eq!(fs::read_dir(&dir).unwrap().count(), 1);
        fs::remove_file(path).unwrap();
        fs::remove_dir(dir).unwrap();
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn ephemeral_caption_remains_readable_but_is_deleted_when_owner_closes() {
        let path = std::env::temp_dir().join(format!(
            "feelsay-ephemeral-test-{}.json",
            std::process::id()
        ));
        let owner = open_ephemeral(&path).unwrap();
        fs::write(&path, "temporary interim words").unwrap();
        assert_eq!(
            fs::read_to_string(&path).unwrap(),
            "temporary interim words"
        );
        drop(owner);
        assert!(!path.exists());
    }
}
