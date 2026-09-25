use crate::app_error::AppError;
use std::{
    mem::{size_of, ManuallyDrop},
    sync::mpsc,
    time::Duration,
};
use windows::{
    core::{implement, Interface, Ref, HRESULT},
    Wdk::System::SystemServices::RtlGetVersion,
    Win32::{
        Media::Audio::*,
        System::{
            Com::{
                StructuredStorage::{
                    PROPVARIANT, PROPVARIANT_0, PROPVARIANT_0_0, PROPVARIANT_0_0_0,
                },
                BLOB,
            },
            SystemInformation::OSVERSIONINFOW,
            Variant::VT_BLOB,
        },
    },
};

pub fn is_supported() -> bool {
    let mut version = OSVERSIONINFOW {
        dwOSVersionInfoSize: size_of::<OSVERSIONINFOW>() as u32,
        ..Default::default()
    };
    unsafe { RtlGetVersion(&mut version).is_ok() && version.dwBuildNumber >= 20348 }
}

pub fn process_id(source: &str) -> Option<u32> {
    let mut fields = source.split(':');
    if fields.next()? != "window" {
        return None;
    }
    let hwnd = usize::from_str_radix(fields.next()?, 16).ok()?;
    let process = fields.next()?.parse::<u32>().ok()?;
    (hwnd != 0 && process != 0 && fields.next().is_none()).then_some(process)
}

pub fn source_is_alive(source: &str) -> bool {
    let Some(process) = process_id(source) else {
        return false;
    };
    let Some(window) = source
        .split(':')
        .nth(1)
        .and_then(|value| usize::from_str_radix(value, 16).ok())
    else {
        return false;
    };
    let hwnd = windows::Win32::Foundation::HWND(window as *mut _);
    unsafe {
        let mut actual_process = 0;
        windows::Win32::UI::WindowsAndMessaging::GetWindowThreadProcessId(
            hwnd,
            Some(&mut actual_process),
        );
        actual_process == process
    }
}

#[implement(IActivateAudioInterfaceCompletionHandler)]
struct Completion {
    sender: mpsc::SyncSender<()>,
}

impl IActivateAudioInterfaceCompletionHandler_Impl for Completion_Impl {
    fn ActivateCompleted(
        &self,
        _: Ref<'_, IActivateAudioInterfaceAsyncOperation>,
    ) -> windows::core::Result<()> {
        let _ = self.sender.try_send(());
        Ok(())
    }
}

pub fn activate(process_id: u32) -> Result<IAudioClient, AppError> {
    if !is_supported() {
        return Err(AppError::Audio(
            "application capture unsupported on this Windows version".into(),
        ));
    }
    let mut activation = AUDIOCLIENT_ACTIVATION_PARAMS {
        ActivationType: AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
        Anonymous: AUDIOCLIENT_ACTIVATION_PARAMS_0 {
            ProcessLoopbackParams: AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS {
                TargetProcessId: process_id,
                ProcessLoopbackMode: PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE,
            },
        },
    };
    // PROPVARIANT's Drop calls PropVariantClear, but this BLOB borrows stack data.
    let params = ManuallyDrop::new(PROPVARIANT {
        Anonymous: PROPVARIANT_0 {
            Anonymous: ManuallyDrop::new(PROPVARIANT_0_0 {
                vt: VT_BLOB,
                Anonymous: PROPVARIANT_0_0_0 {
                    blob: BLOB {
                        cbSize: size_of::<AUDIOCLIENT_ACTIVATION_PARAMS>() as u32,
                        pBlobData: (&mut activation as *mut AUDIOCLIENT_ACTIVATION_PARAMS).cast(),
                    },
                },
                ..Default::default()
            }),
        },
    });
    let (sender, receiver) = mpsc::sync_channel(1);
    let handler: IActivateAudioInterfaceCompletionHandler = Completion { sender }.into();
    unsafe {
        let operation = ActivateAudioInterfaceAsync(
            VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
            &IAudioClient::IID,
            Some(&*params),
            &handler,
        )
        .map_err(|error| AppError::Audio(error.to_string()))?;
        receiver.recv_timeout(Duration::from_secs(5)).map_err(|_| {
            AppError::Audio(
                "Application audio did not respond. Select the source again or use system audio."
                    .into(),
            )
        })?;
        let mut result = HRESULT(0);
        let mut interface = None;
        operation
            .GetActivateResult(&mut result, &mut interface)
            .map_err(|error| AppError::Audio(error.to_string()))?;
        result
            .ok()
            .map_err(|error| AppError::Audio(error.to_string()))?;
        interface
            .ok_or_else(|| AppError::Audio("Application audio is unavailable".into()))?
            .cast()
            .map_err(|error| AppError::Audio(error.to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_valid_window_sources_resolve_to_process_capture() {
        assert_eq!(process_id("window:abcd:42"), Some(42));
        for value in [
            "system-audio",
            "window:0:42",
            "window:abcd:0",
            "window:abcd:42:extra",
            "window:abcd:-1",
        ] {
            assert_eq!(process_id(value), None);
        }
    }
}
