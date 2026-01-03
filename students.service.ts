import { Injectable, NotFoundException, BadRequestException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Student } from '../entities/student.entity';
import { Schedule } from '../entities/schedule.entity';
import { AttendanceSession, SessionStatus } from '../entities/attendance-session.entity';
import { AttendanceRecord, AttendanceStatus } from '../entities/attendance-record.entity';
import { Subject } from '../entities/subject.entity';
import { Class } from '../entities/class.entity';
import { Teacher } from '../entities/teacher.entity';
import { User } from '../entities/user.entity';
import { QrToken } from '../entities/qr-token.entity';
import * as crypto from 'crypto';

@Injectable()
export class StudentsService {
  constructor(
    @InjectRepository(Student)
    private studentRepository: Repository<Student>,
    @InjectRepository(Schedule)
    private scheduleRepository: Repository<Schedule>,
    @InjectRepository(AttendanceSession)
    private attendanceSessionRepository: Repository<AttendanceSession>,
    @InjectRepository(AttendanceRecord)
    private attendanceRecordRepository: Repository<AttendanceRecord>,
    @InjectRepository(Subject)
    private subjectRepository: Repository<Subject>,
    @InjectRepository(Class)
    private classRepository: Repository<Class>,
    @InjectRepository(Teacher)
    private teacherRepository: Repository<Teacher>,
    @InjectRepository(User)
    private userRepository: Repository<User>,
    @InjectRepository(QrToken)
    private qrTokenRepository: Repository<QrToken>,
  ) {}

  /**
   * Convert Indonesian status to English for frontend
   */
  private convertStatusToEnglish(status: string): string {
    const statusMap = {
      'Hadir': 'present',
      'Alpha': 'absent',
      'Sakit': 'sick',
      'Izin': 'permit',
    };
    return statusMap[status] || status.toLowerCase();
  }

  /**
   * Get student's subjects (schedule grouped by subject)
   */
  async getStudentSubjects(userId: number) {
    const student = await this.studentRepository.findOne({
      where: { user_id: userId },
      relations: ['class'],
    });

    if (!student) {
      throw new NotFoundException('Student not found');
    }

    // Get all schedules for this class
    const schedules = await this.scheduleRepository
      .createQueryBuilder('schedule')
      .leftJoinAndSelect('schedule.subject', 'subject')
      .leftJoinAndSelect('schedule.teacher', 'teacher')
      .leftJoinAndSelect('teacher.user', 'teacherUser')
      .where('schedule.class_id = :classId', { classId: student.class_id })
      .orderBy('schedule.day_of_week', 'ASC')
      .addOrderBy('schedule.start_time', 'ASC')
      .getMany();

    // Group by subject
    const subjectsMap = new Map();
    schedules.forEach((schedule) => {
      const subjectId = schedule.subject.id;
      if (!subjectsMap.has(subjectId)) {
        subjectsMap.set(subjectId, {
          subject: schedule.subject.name,
          subject_code: schedule.subject.code,
          teacher: schedule.teacher.user.name,
          teacher_qualification: schedule.teacher.qualification,
          schedules: [],
        });
      }
      subjectsMap.get(subjectId).schedules.push({
        day: schedule.day_of_week,
        time: `${schedule.start_time.substring(0, 5)} - ${schedule.end_time.substring(0, 5)}`,
      });
    });

    return Array.from(subjectsMap.values());
  }

  /**
   * Get student's attendance history for a specific subject
   */
  async getSubjectAttendanceHistory(userId: number, subjectName: string) {
    const student = await this.studentRepository.findOne({
      where: { user_id: userId },
    });

    if (!student) {
      throw new NotFoundException('Student not found');
    }

    // Find subject
    const subject = await this.subjectRepository.findOne({
      where: { name: subjectName },
    });

    if (!subject) {
      throw new NotFoundException('Subject not found');
    }

    // Get all attendance records for this student and subject
    const records = await this.attendanceRecordRepository
      .createQueryBuilder('record')
      .innerJoin('record.session', 'session')
      .innerJoin('session.schedule', 'schedule')
      .innerJoin('schedule.subject', 'subject')
      .innerJoin('schedule.teacher', 'teacher')
      .innerJoin('teacher.user', 'teacherUser')
      .where('record.student_id = :studentId', { studentId: student.id })
      .andWhere('subject.id = :subjectId', { subjectId: subject.id })
      .select([
        'record.id',
        'record.status',
        'record.notes',
        'session.session_date',
        'schedule.start_time',
        'schedule.end_time',
        'teacherUser.name',
        'teacher.qualification',
      ])
      .orderBy('session.session_date', 'DESC')
      .addOrderBy('schedule.start_time', 'ASC')
      .getRawMany();

    let meetingCounter = 1;
    return records.map((record) => ({
      name: `Pertemuan ${meetingCounter++}`,
      time: `${record.schedule_start_time.substring(0, 5)} - ${record.schedule_end_time.substring(0, 5)}`,
      teacher: `${record.teacherUser_name} ${record.teacher_qualification || ''}`.trim(),
      status: this.convertStatusToEnglish(record.record_status),
      date: record.session_session_date,
      notes: record.record_notes,
    }));
  }

  /**
   * Get student's weekly schedule
   */
  async getStudentSchedule(userId: number, day?: string) {
    const student = await this.studentRepository.findOne({
      where: { user_id: userId },
    });

    if (!student) {
      throw new NotFoundException('Student not found');
    }

    const query = this.scheduleRepository
      .createQueryBuilder('schedule')
      .leftJoinAndSelect('schedule.subject', 'subject')
      .leftJoinAndSelect('schedule.teacher', 'teacher')
      .leftJoinAndSelect('teacher.user', 'teacherUser')
      .where('schedule.class_id = :classId', { classId: student.class_id })
      .orderBy('schedule.day_of_week', 'ASC')
      .addOrderBy('schedule.start_time', 'ASC');

    if (day) {
      query.andWhere('schedule.day_of_week = :day', { day });
    }

    const schedules = await query.getMany();

    return schedules.map((schedule) => ({
      id: schedule.id,
      subject: schedule.subject.name,
      subject_code: schedule.subject.code,
      time: `${schedule.start_time.substring(0, 5)} - ${schedule.end_time.substring(0, 5)}`,
      teacher: schedule.teacher?.user?.name || 'Unknown',
      teacher_qualification: schedule.teacher?.qualification || '',
      room: schedule.room,
      day: schedule.day_of_week,
    }));
  }

  /**
   * Get student's attendance history (all subjects)
   */
  async getAttendanceHistory(userId: number) {
    const student = await this.studentRepository.findOne({
      where: { user_id: userId },
    });

    if (!student) {
      throw new NotFoundException('Student not found');
    }

    // Get all attendance records grouped by date
    const records = await this.attendanceRecordRepository
      .createQueryBuilder('record')
      .innerJoin('record.session', 'session')
      .innerJoin('session.schedule', 'schedule')
      .innerJoin('schedule.subject', 'subject')
      .innerJoin('schedule.teacher', 'teacher')
      .innerJoin('teacher.user', 'teacherUser')
      .where('record.student_id = :studentId', { studentId: student.id })
      .select([
        'record.id',
        'record.status',
        'record.notes',
        'session.session_date',
        'schedule.start_time',
        'schedule.end_time',
        'subject.name',
        'teacherUser.name',
        'teacher.qualification',
      ])
      .orderBy('session.session_date', 'DESC')
      .addOrderBy('schedule.start_time', 'ASC')
      .getRawMany();

    // Group by date
    const groupedByDate = records.reduce((acc, record) => {
      const dateKey = record.session_session_date;
      if (!acc[dateKey]) {
        acc[dateKey] = [];
      }
      acc[dateKey].push({
        subject: record.subject_name,
        time: `${record.schedule_start_time.substring(0, 5)} - ${record.schedule_end_time.substring(0, 5)}`,
        teacher: `${record.teacherUser_name} ${record.teacher_qualification || ''}`.trim(),
        status: this.convertStatusToEnglish(record.record_status),
        notes: record.record_notes,
      });
      return acc;
    }, {});

    // Convert to array format with date headers
    const result = [];
    Object.keys(groupedByDate)
      .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())
      .forEach((date) => {
        result.push({
          type: 'date',
          date: this.formatDate(new Date(date)),
        });
        groupedByDate[date].forEach((entry) => {
          result.push({
            type: 'entry',
            ...entry,
          });
        });
      });

    return result;
  }

  /**
   * Get student's attendance statistics
   */
  async getAttendanceStats(userId: number, period: string = '1 Bulan') {
    const student = await this.studentRepository.findOne({
      where: { user_id: userId },
    });

    if (!student) {
      throw new NotFoundException('Student not found');
    }

    // Calculate date range based on period
    const endDate = new Date();
    const startDate = new Date();
    
    switch (period) {
      case '1 Minggu':
        startDate.setDate(startDate.getDate() - 7);
        break;
      case '1 Bulan':
        startDate.setMonth(startDate.getMonth() - 1);
        break;
      case '3 Bulan':
        startDate.setMonth(startDate.getMonth() - 3);
        break;
      case '6 Bulan':
        startDate.setMonth(startDate.getMonth() - 6);
        break;
      case '1 Tahun':
        startDate.setFullYear(startDate.getFullYear() - 1);
        break;
      default:
        startDate.setMonth(startDate.getMonth() - 1);
    }

    // Get attendance records in the period
    const records = await this.attendanceRecordRepository
      .createQueryBuilder('record')
      .innerJoin('record.session', 'session')
      .where('record.student_id = :studentId', { studentId: student.id })
      .andWhere('session.session_date >= :startDate', { startDate })
      .andWhere('session.session_date <= :endDate', { endDate })
      .select('record.status', 'status')
      .addSelect('COUNT(*)', 'count')
      .groupBy('record.status')
      .getRawMany();

    const stats = {
      present: 0,
      absent: 0,
      sick: 0,
      permit: 0,
    };

    records.forEach((record) => {
      const status = this.convertStatusToEnglish(record.status);
      if (status in stats) {
        stats[status] = parseInt(record.count);
      }
    });

    return stats;
  }

  /**
   * Format date to Indonesian format
   */
  private formatDate(date: Date): string {
    const days = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'];
    const months = [
      'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
      'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
    ];

    const dayName = days[date.getDay()];
    const day = date.getDate();
    const month = months[date.getMonth()];
    const year = date.getFullYear();

    return `${dayName}, ${day} ${month} ${year}`;
  }

  /**
   * Generate QR token for student
   */
  async generateQRToken(userId: number) {
    const student = await this.studentRepository.findOne({
      where: { user_id: userId },
      relations: ['user', 'class'],
    });

    if (!student) {
      throw new NotFoundException('Student not found');
    }

    // Check if student already has an active (unused and not expired) token
    const existingToken = await this.qrTokenRepository.findOne({
      where: {
        student_id: student.id,
        is_used: false,
      },
    });

    if (existingToken) {
      const now = new Date();
      if (now < existingToken.expires_at) {
        // Return existing token instead of creating new one
        return {
          token: existingToken.token,
          student_id: student.id,
          student_name: student.user.name,
          student_number: student.student_number,
          generated_at: existingToken.generated_at,
          expires_at: existingToken.expires_at,
          expires_in_seconds: Math.floor((existingToken.expires_at.getTime() - now.getTime()) / 1000),
        };
      }
    }

    // Generate unique token - ultra short format for QR compatibility
    // Use only 6-character random hex string
    const randomStr = crypto.randomBytes(3).toString('hex'); // 6 chars
    const token = randomStr; // Just the random string

    const now = new Date();
    const expiresAt = new Date(now.getTime() + 60 * 60 * 1000); // 1 hour expiry

    // Invalidate any previous unused tokens for this student
    await this.qrTokenRepository.update(
      {
        student_id: student.id,
        is_used: false,
      },
      {
        is_used: true,
        used_at: now,
      },
    );

    // Create new token
    const qrToken = this.qrTokenRepository.create({
      student_id: student.id,
      token,
      generated_at: now,
      expires_at: expiresAt,
      is_used: false,
    });

    await this.qrTokenRepository.save(qrToken);

    return {
      token,
      student_id: student.id,
      student_name: student.user.name,
      student_number: student.student_number,
      generated_at: now,
      expires_at: expiresAt,
      expires_in_seconds: 3600,
    };
  }

  /**
   * Validate QR token and mark attendance
   */
  async validateQRToken(token: string, sessionId?: number) {
    // Find the token
    const qrToken = await this.qrTokenRepository.findOne({
      where: { token },
      relations: ['student', 'student.user', 'student.class'],
    });

    if (!qrToken) {
      throw new BadRequestException('Token tidak valid');
    }

    // Check if token is already used
    if (qrToken.is_used) {
      throw new BadRequestException('Token sudah digunakan');
    }

    // Check if token is expired
    const now = new Date();
    if (now > qrToken.expires_at) {
      throw new BadRequestException('Token sudah kadaluarsa');
    }

    // Find active session for this student's class
    let session: AttendanceSession;
    
    if (sessionId) {
      session = await this.attendanceSessionRepository.findOne({
        where: { id: sessionId },
        relations: ['schedule', 'schedule.subject', 'schedule.teacher', 'schedule.teacher.user'],
      });
    } else {
      // Find current active session based on time and day
      const currentTime = now.toTimeString().substring(0, 8);
      const dayNames = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'];
      const currentDay = dayNames[now.getDay()];

      const schedule = await this.scheduleRepository
        .createQueryBuilder('schedule')
        .where('schedule.class_id = :classId', { classId: qrToken.student.class_id })
        .andWhere('schedule.day_of_week = :day', { day: currentDay })
        .andWhere('schedule.start_time <= :currentTime', { currentTime })
        .andWhere('schedule.end_time >= :currentTime', { currentTime })
        .andWhere('schedule.is_active = :isActive', { isActive: true })
        .leftJoinAndSelect('schedule.subject', 'subject')
        .leftJoinAndSelect('schedule.teacher', 'teacher')
        .leftJoinAndSelect('teacher.user', 'teacherUser')
        .getOne();

      if (!schedule) {
        throw new BadRequestException('Tidak ada jadwal aktif saat ini');
      }

      // Find or create session for today
      const sessionDate = now.toISOString().split('T')[0];
      const sessionDateObj = new Date(sessionDate);
      session = await this.attendanceSessionRepository.findOne({
        where: {
          schedule_id: schedule.id,
          session_date: sessionDateObj,
        },
        relations: ['schedule', 'schedule.subject', 'schedule.teacher', 'schedule.teacher.user'],
      });

      if (!session) {
        session = this.attendanceSessionRepository.create({
          schedule_id: schedule.id,
          session_date: sessionDateObj,
          start_time: schedule.start_time,
          end_time: schedule.end_time,
          teacher_id: schedule.teacher_id,
          status: SessionStatus.SCHEDULED,
        });
        await this.attendanceSessionRepository.save(session);
        session.schedule = schedule;
      }
    }

    if (!session) {
      throw new BadRequestException('Sesi tidak ditemukan');
    }

    // Check if student already has attendance for this session
    const existingRecord = await this.attendanceRecordRepository.findOne({
      where: {
        session_id: session.id,
        student_id: qrToken.student_id,
      },
    });

    if (existingRecord) {
      throw new BadRequestException('Anda sudah melakukan absensi untuk kelas ini');
    }

    // Create attendance record
    const attendanceRecord = this.attendanceRecordRepository.create({
      session_id: session.id,
      student_id: qrToken.student_id,
      status: 'Hadir' as any, // Using Indonesian status directly
      check_in_time: now,
      qr_token: token,
    });

    await this.attendanceRecordRepository.save(attendanceRecord);

    // Mark token as used
    qrToken.is_used = true;
    qrToken.used_at = now;
    qrToken.session_id = session.id;
    await this.qrTokenRepository.save(qrToken);

    // Format time for display
    const checkInTime = now.toLocaleString('id-ID', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });

    return {
      success: true,
      message: 'Absensi berhasil',
      data: {
        student_name: qrToken.student.user.name,
        student_number: qrToken.student.student_number,
        subject: session.schedule.subject.name,
        teacher: session.schedule.teacher.user.name,
        check_in_time: checkInTime,
        status: 'Hadir',
        session_id: session.id,
        record_id: attendanceRecord.id,
      },
    };
  }

  /**
   * Get latest attendance record for student
   */
  async getLatestAttendance(userId: number) {
    const student = await this.studentRepository.findOne({
      where: { user_id: userId },
    });

    if (!student) {
      throw new NotFoundException('Student not found');
    }

    const latestRecord = await this.attendanceRecordRepository
      .createQueryBuilder('record')
      .leftJoinAndSelect('record.session', 'session')
      .leftJoinAndSelect('session.schedule', 'schedule')
      .leftJoinAndSelect('schedule.subject', 'subject')
      .leftJoinAndSelect('schedule.teacher', 'teacher')
      .leftJoinAndSelect('teacher.user', 'teacherUser')
      .where('record.student_id = :studentId', { studentId: student.id })
      .orderBy('record.created_at', 'DESC')
      .getOne();

    if (!latestRecord) {
      return null;
    }

    // Format time
    const checkInTime = new Date(latestRecord.check_in_time || latestRecord.created_at).toLocaleString('id-ID', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });

    return {
      student_name: student.user?.name || 'Unknown',
      student_number: student.student_number,
      subject: latestRecord.session.schedule.subject.name,
      teacher: latestRecord.session.schedule.teacher.user.name,
      check_in_time: checkInTime,
      status: this.convertStatusToEnglish(latestRecord.status),
      session_id: latestRecord.session_id,
      record_id: latestRecord.id,
    };
  }

  /**
   * Check if specific QR token was scanned and return attendance
   */
  async checkQRTokenAttendance(userId: number, token: string) {
    const student = await this.studentRepository.findOne({
      where: { user_id: userId },
      relations: ['user'],
    });

    if (!student) {
      throw new NotFoundException('Student not found');
    }

    // Find the QR token
    const qrToken = await this.qrTokenRepository.findOne({
      where: {
        token: token,
        student_id: student.id,
      },
    });

    if (!qrToken) {
      throw new NotFoundException('QR token not found');
    }

    // Check if token is expired
    const now = new Date();
    if (now > qrToken.expires_at) {
      return {
        scanned: false,
        expired: true,
        message: 'QR code sudah kadaluarsa',
      };
    }

    // Check if token was used
    if (!qrToken.is_used || !qrToken.session_id) {
      return {
        scanned: false,
        expired: false,
        message: 'QR code belum di-scan',
      };
    }

    // Token was used, get the attendance record
    const attendanceRecord = await this.attendanceRecordRepository
      .createQueryBuilder('record')
      .leftJoinAndSelect('record.session', 'session')
      .leftJoinAndSelect('session.schedule', 'schedule')
      .leftJoinAndSelect('schedule.subject', 'subject')
      .leftJoinAndSelect('schedule.teacher', 'teacher')
      .leftJoinAndSelect('teacher.user', 'teacherUser')
      .where('record.student_id = :studentId', { studentId: student.id })
      .andWhere('record.session_id = :sessionId', { sessionId: qrToken.session_id })
      .getOne();

    if (!attendanceRecord) {
      return {
        scanned: true,
        expired: false,
        message: 'QR code sudah di-scan tapi data absensi tidak ditemukan',
      };
    }

    // Format time
    const checkInTime = new Date(attendanceRecord.check_in_time || attendanceRecord.created_at).toLocaleString('id-ID', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });

    return {
      scanned: true,
      expired: false,
      student_name: student.user.name,
      student_number: student.student_number,
      subject: attendanceRecord.session.schedule.subject.name,
      teacher: attendanceRecord.session.schedule.teacher.user.name,
      check_in_time: checkInTime,
      status: this.convertStatusToEnglish(attendanceRecord.status),
      session_id: attendanceRecord.session_id,
      record_id: attendanceRecord.id,
    };
  }
}
